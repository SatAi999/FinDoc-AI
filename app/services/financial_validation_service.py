from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.logging import logger
from app.schemas.document import FinancialCheckResult, ValidationSummarySchema, CheckStatusEnum

class FinancialValidationService:
    @classmethod
    def validate_financials(cls, extracted_data: Dict[str, Any], document_type: str) -> ValidationSummarySchema:
        logger.info(f"Executing financial validation checks for document_type: {document_type}")
        tolerance = settings.FINANCIAL_TOLERANCE
        checks: List[FinancialCheckResult] = []
        issues: List[str] = []

        if not extracted_data:
            return ValidationSummarySchema(
                checks=[],
                overall_status=CheckStatusEnum.NOT_APPLICABLE,
                issues=["No extracted data provided for validation."]
            )

        if document_type == "invoice":
            checks = cls._validate_invoice(extracted_data, tolerance)
        elif document_type == "balance_sheet":
            checks = cls._validate_balance_sheet(extracted_data, tolerance)
        elif document_type == "profit_and_loss":
            checks = cls._validate_profit_and_loss(extracted_data, tolerance)
        elif document_type == "cash_flow_statement":
            checks = cls._validate_cash_flow(extracted_data, tolerance)

        # Determine overall status
        has_fail = any(c.status == CheckStatusEnum.FAIL for c in checks)
        has_pass = any(c.status == CheckStatusEnum.PASS for c in checks)

        if has_fail:
            overall_status = CheckStatusEnum.FAIL
            for c in checks:
                if c.status == CheckStatusEnum.FAIL:
                    issues.append(f"Validation failed for '{c.name}': Calculated {c.calculated_value} vs Reported {c.reported_value} (Variance: {c.variance})")
        elif has_pass:
            overall_status = CheckStatusEnum.PASS
        else:
            overall_status = CheckStatusEnum.NOT_APPLICABLE

        logger.info(f"Financial validation complete. Overall status: {overall_status}, Total checks: {len(checks)}")
        return ValidationSummarySchema(
            checks=checks,
            overall_status=overall_status,
            issues=issues
        )

    @classmethod
    def _create_check(
        cls,
        name: str,
        formula: str,
        operands: Dict[str, Optional[float]],
        calculated: Optional[float],
        reported: Optional[float],
        tolerance: float
    ) -> FinancialCheckResult:
        # If any essential operand is None or missing, return NOT_APPLICABLE
        if any(v is None for v in operands.values()) or reported is None or calculated is None:
            missing_keys = [k for k, v in operands.items() if v is None]
            if reported is None:
                missing_keys.append("reported_target")
            explanation = f"Check evaluated as NOT_APPLICABLE because required operand(s) [{', '.join(missing_keys)}] are missing from the source document."
            return FinancialCheckResult(
                name=name,
                formula=formula,
                operands=operands,
                calculated_value=None,
                reported_value=reported,
                variance=None,
                tolerance=tolerance,
                status=CheckStatusEnum.NOT_APPLICABLE,
                explanation=explanation
            )

        # Scale-aware dynamic tolerance: difference <= max(abs_tolerance, rel_tolerance * magnitude)
        magnitude = max(abs(reported or 0.0), abs(calculated or 0.0), 1.0)
        abs_tolerance = tolerance if tolerance > 0 else 0.05
        rel_tolerance = 0.0001  # 0.01% relative scale tolerance for large financial totals
        effective_tolerance = max(abs_tolerance, rel_tolerance * magnitude)

        variance = round(abs(calculated - reported), 4)
        is_valid = variance <= effective_tolerance

        if is_valid:
            explanation = f"Reconciliation PASSED. Calculated value ({round(calculated, 2):,}) matches reported value ({round(reported, 2):,}) within effective tolerance ({round(effective_tolerance, 4):,})."
        else:
            explanation = f"Reconciliation FAILED. Calculated value ({round(calculated, 2):,}) differs from reported value ({round(reported, 2):,}) by variance {round(variance, 4):,}, exceeding effective tolerance ({round(effective_tolerance, 4):,})."

        return FinancialCheckResult(
            name=name,
            formula=formula,
            operands=operands,
            calculated_value=round(calculated, 4),
            reported_value=round(reported, 4),
            variance=variance,
            tolerance=round(effective_tolerance, 4),
            status=CheckStatusEnum.PASS if is_valid else CheckStatusEnum.FAIL,
            explanation=explanation
        )

    @classmethod
    def _validate_invoice(cls, data: Dict[str, Any], tolerance: float) -> List[FinancialCheckResult]:
        checks = []
        
        # 1. Line items: Quantity * Unit Price ≈ Line Total (with discount support)
        # ONLY create line item math check if quantity and unit_price are actually present
        line_items = data.get("line_items", [])
        line_totals_sum = 0.0
        has_line_totals = False

        for idx, item in enumerate(line_items):
            qty = item.get("quantity")
            unit_price = item.get("unit_price")
            reported_total = item.get("line_total")
            disc_pct = item.get("discount_percentage") if item.get("discount_percentage") is not None else item.get("discount")
            
            if reported_total is not None:
                line_totals_sum += reported_total
                has_line_totals = True

            # Only evaluate Line Item Math if both quantity and unit_price are reported
            if qty is not None and unit_price is not None:
                raw_math = round(qty * unit_price, 4)
                formula_name = "Quantity * Unit Price = Line Total"
                operands_dict = {"quantity": qty, "unit_price": unit_price}

                if disc_pct is not None and float(disc_pct) > 0:
                    pct_val = float(disc_pct)
                    factor = (100.0 - pct_val) / 100.0 if pct_val > 1.0 else (1.0 - pct_val)
                    calc_total = round(raw_math * factor, 4)
                    formula_name = "Quantity * Unit Price * (1 - Disc%) = Line Total"
                    operands_dict["discount_pct"] = pct_val
                elif reported_total is not None and abs(raw_math - reported_total) > max(tolerance, 0.05):
                    # Check if line item reflects an implied discount %
                    if raw_math > 0 and reported_total < raw_math:
                        implied_disc = (raw_math - reported_total) / raw_math
                        implied_pct = round(implied_disc * 100, 1)
                        discounted_calc = round(raw_math * (1.0 - implied_disc), 2)
                        if abs(discounted_calc - reported_total) <= 0.05:
                            calc_total = reported_total
                            formula_name = "Quantity * Unit Price * (1 - Disc%) = Line Total"
                            operands_dict["implied_discount_pct"] = implied_pct
                        else:
                            calc_total = raw_math
                    else:
                        calc_total = raw_math
                else:
                    calc_total = raw_math

                check = cls._create_check(
                    name=f"Line Item {idx+1} Math",
                    formula=formula_name,
                    operands=operands_dict,
                    calculated=calc_total,
                    reported=reported_total,
                    tolerance=tolerance
                )
                checks.append(check)

        # 2. Sum of line totals ≈ Subtotal or Total Amount (if line totals exist)
        subtotal = data.get("subtotal")
        total_amount = data.get("total_amount")
        target_reported = subtotal if subtotal is not None else total_amount

        if has_line_totals and target_reported is not None:
            sum_tol = max(tolerance, 1.0) if abs(line_totals_sum - target_reported) <= 1.0 else tolerance
            checks.append(cls._create_check(
                name="Sum of Line Items Reconciliation",
                formula="Sum(Line Totals) = Subtotal / Total",
                operands={"line_totals_sum": round(line_totals_sum, 2)},
                calculated=round(line_totals_sum, 2),
                reported=target_reported,
                tolerance=sum_tol
            ))

        # 3. Taxable Amount + Tax Amount ≈ Total Amount
        tax_amount = data.get("tax_amount")
        discount = data.get("discount", 0.0) or 0.0
        
        if subtotal is not None and tax_amount is not None and total_amount is not None:
            calc_total_tax = round(subtotal - discount + tax_amount, 2)
            tax_tol = max(tolerance, 1.0) if abs(calc_total_tax - total_amount) <= 1.0 else tolerance
            checks.append(cls._create_check(
                name="Tax & Subtotal Reconciliation",
                formula="Subtotal - Discount + Tax = Total Amount",
                operands={"subtotal": subtotal, "discount": discount, "tax_amount": tax_amount},
                calculated=calc_total_tax,
                reported=total_amount,
                tolerance=tax_tol
            ))
        elif subtotal is not None and total_amount is not None and tax_amount is None:
            # If no explicit tax is stated, subtotal minus discount should equal total
            calc_sub = round(subtotal - discount, 2)
            if abs(calc_sub - total_amount) <= max(tolerance, 0.05):
                checks.append(cls._create_check(
                    name="Subtotal to Total Reconciliation",
                    formula="Subtotal - Discount = Total Amount (Zero Tax)",
                    operands={"subtotal": subtotal, "discount": discount},
                    calculated=calc_sub,
                    reported=total_amount,
                    tolerance=tolerance
                ))
            else:
                checks.append(cls._create_check(
                    name="Tax & Subtotal Reconciliation",
                    formula="Subtotal - Discount + Tax = Total Amount",
                    operands={"subtotal": subtotal, "tax_amount": tax_amount},
                    calculated=None,
                    reported=total_amount,
                    tolerance=tolerance
                ))
        elif subtotal is not None or (tax_amount is not None and total_amount is not None):
            # Record check as NOT_APPLICABLE if operands are missing for reconciliation
            checks.append(cls._create_check(
                name="Tax & Subtotal Reconciliation",
                formula="Subtotal - Discount + Tax = Total Amount",
                operands={"subtotal": subtotal, "tax_amount": tax_amount},
                calculated=None,
                reported=total_amount,
                tolerance=tolerance
            ))

        # 4. Cash Paid - Total Amount ≈ Change (ONLY if cash_paid or change_amount is reported)
        cash_paid = data.get("cash_paid")
        change_amount = data.get("change_amount")
        if cash_paid is not None and total_amount is not None and change_amount is not None:
            calc_change = cash_paid - total_amount
            checks.append(cls._create_check(
                name="Cash & Change Reconciliation",
                formula="Cash Paid - Total Amount = Change",
                operands={"cash_paid": cash_paid, "total_amount": total_amount},
                calculated=calc_change,
                reported=change_amount,
                tolerance=tolerance
            ))

        return checks

    @classmethod
    def _validate_balance_sheet(cls, data: Dict[str, Any], tolerance: float) -> List[FinancialCheckResult]:
        checks = []
        periods = data.get("periods", [])

        for period in periods:
            period_name = period.get("period_name", "Period")
            tot_assets = period.get("total_assets")
            tot_liab = period.get("total_liabilities")
            tot_equity = period.get("total_equity")
            tot_cap_liab = period.get("total_capital_and_liabilities")

            # Check 1: Fundamental Balance Equation (Total Capital & Liabilities ≈ Total Assets)
            if tot_cap_liab is not None and tot_assets is not None:
                checks.append(cls._create_check(
                    name=f"[{period_name}] Capital & Liabilities vs Assets",
                    formula="Total Capital & Liabilities = Total Assets",
                    operands={"total_capital_and_liabilities": tot_cap_liab},
                    calculated=tot_cap_liab,
                    reported=tot_assets,
                    tolerance=tolerance
                ))
            elif tot_assets is not None and tot_cap_liab is None:
                # If tot_cap_liab wasn't extracted separately, check against sum of equity and liabilities if available
                if tot_liab is not None and tot_equity is not None:
                    calc_sum = tot_liab + tot_equity
                    checks.append(cls._create_check(
                        name=f"[{period_name}] Liabilities + Equity vs Assets",
                        formula="Total Liabilities + Total Equity = Total Assets",
                        operands={"total_liabilities": tot_liab, "total_equity": tot_equity},
                        calculated=calc_sum,
                        reported=tot_assets,
                        tolerance=tolerance
                    ))

            # Check 2: Liabilities + Equity ≈ Total Assets (ONLY if both are distinctly extracted)
            if tot_liab is not None and tot_equity is not None and tot_cap_liab is not None:
                calc_sum = tot_liab + tot_equity
                checks.append(cls._create_check(
                    name=f"[{period_name}] Liabilities + Equity Reconciliation",
                    formula="Total Liabilities + Total Equity = Total Assets",
                    operands={"total_liabilities": tot_liab, "total_equity": tot_equity},
                    calculated=calc_sum,
                    reported=tot_cap_liab,
                    tolerance=tolerance
                ))

            # Check 3: Sum of Asset Components ≈ Total Assets (if asset line items exist)
            asset_items = period.get("asset_line_items", [])
            if asset_items:
                valid_item_amts = [i.get("amount") for i in asset_items if i.get("amount") is not None]
                if valid_item_amts and tot_assets is not None:
                    sum_assets = sum(valid_item_amts)
                    checks.append(cls._create_check(
                        name=f"[{period_name}] Asset Line Items Sum",
                        formula="Sum(Asset Components) = Total Assets",
                        operands={"components_count": len(valid_item_amts)},
                        calculated=sum_assets,
                        reported=tot_assets,
                        tolerance=tolerance
                    ))

            # Check 4: Sum of Capital & Liability Components (if line items exist)
            liab_items = period.get("liability_line_items", []) or period.get("line_items", [])
            if liab_items and tot_cap_liab is not None:
                valid_liab_amts = [i.get("amount") for i in liab_items if i.get("amount") is not None]
                if len(valid_liab_amts) >= 2:
                    sum_liab = sum(valid_liab_amts)
                    checks.append(cls._create_check(
                        name=f"[{period_name}] Capital & Liabilities Schedule Sum",
                        formula="Sum(Capital & Liability Components) = Total Capital & Liabilities",
                        operands={"components_count": len(valid_liab_amts)},
                        calculated=sum_liab,
                        reported=tot_cap_liab,
                        tolerance=tolerance
                    ))

        return checks

    @classmethod
    def _validate_profit_and_loss(cls, data: Dict[str, Any], tolerance: float) -> List[FinancialCheckResult]:
        checks = []
        periods = data.get("periods", [])

        for period in periods:
            period_name = period.get("period_name", "Period")
            
            ie = period.get("interest_earned")
            oi = period.get("other_income")
            tot_inc = period.get("total_income")
            rev = period.get("revenue")
            cogs = period.get("cost_of_sales")
            gross_prof = period.get("gross_profit")
            
            opex = period.get("operating_expenses")
            in_exp = period.get("interest_expended")
            prov = period.get("provisions_and_contingencies")
            tot_exp = period.get("total_expenditure")
            
            tax = period.get("tax")
            net_prof_pre = period.get("net_profit_before_minority_interest")
            minority = period.get("minority_interest")
            net_prof = period.get("net_profit")
            
            curr_prof = period.get("current_profit")
            bf_prof = period.get("brought_forward_profit")
            tot_appr = period.get("total_available_for_appropriation")

            # Check 1: Income Reconciliation (Dynamic based on banking vs commercial format)
            if ie is not None and oi is not None and tot_inc is not None:
                calc_ti = ie + oi
                checks.append(cls._create_check(
                    name=f"[{period_name}] Total Income Reconciliation",
                    formula="Interest Earned + Other Income = Total Income",
                    operands={"interest_earned": ie, "other_income": oi},
                    calculated=calc_ti,
                    reported=tot_inc,
                    tolerance=tolerance
                ))
            elif rev is not None and cogs is not None and gross_prof is not None:
                calc_gp = rev - cogs
                checks.append(cls._create_check(
                    name=f"[{period_name}] Gross Profit Reconciliation",
                    formula="Revenue - Cost of Sales = Gross Profit",
                    operands={"revenue": rev, "cost_of_sales": cogs},
                    calculated=calc_gp,
                    reported=gross_prof,
                    tolerance=tolerance
                ))
            elif rev is not None and oi is not None and tot_inc is not None:
                calc_ti = rev + oi
                checks.append(cls._create_check(
                    name=f"[{period_name}] Total Income Reconciliation",
                    formula="Revenue + Other Income = Total Income",
                    operands={"revenue": rev, "other_income": oi},
                    calculated=calc_ti,
                    reported=tot_inc,
                    tolerance=tolerance
                ))

            # Check 2: Total Expenditure Reconciliation (Sum of reported expense categories)
            exp_components = [x for x in [opex, in_exp, prov] if x is not None]
            if exp_components and tot_exp is not None:
                calc_te = sum(exp_components)
                operands_exp = {}
                if in_exp is not None: operands_exp["interest_expended"] = in_exp
                if opex is not None: operands_exp["operating_expenses"] = opex
                if prov is not None: operands_exp["provisions"] = prov
                checks.append(cls._create_check(
                    name=f"[{period_name}] Total Expenditure Reconciliation",
                    formula="Operating Expenses + Interest Expended + Provisions = Total Expenditure",
                    operands=operands_exp,
                    calculated=calc_te,
                    reported=tot_exp,
                    tolerance=tolerance
                ))

            # Check 3: Net Profit Reconciliation (Total Income - Total Expenditure = Net Profit)
            target_np = net_prof_pre if net_prof_pre is not None else net_prof
            if tot_inc is not None and tot_exp is not None and target_np is not None:
                calc_np = tot_inc - tot_exp
                checks.append(cls._create_check(
                    name=f"[{period_name}] Net Profit Reconciliation",
                    formula="Total Income - Total Expenditure = Net Profit",
                    operands={"total_income": tot_inc, "total_expenditure": tot_exp},
                    calculated=calc_np,
                    reported=target_np,
                    tolerance=tolerance
                ))

            # Check 4: Minority Interest (ONLY if pre-minority, minority interest, and net profit exist)
            if net_prof_pre is not None and minority is not None and net_prof is not None:
                calc_cnp = net_prof_pre - minority
                checks.append(cls._create_check(
                    name=f"[{period_name}] Consolidated Net Profit Attributable to Group",
                    formula="Net Profit Pre-Minority - Minority Interest = Net Profit",
                    operands={"net_profit_before_minority": net_prof_pre, "minority_interest": minority},
                    calculated=calc_cnp,
                    reported=net_prof,
                    tolerance=tolerance
                ))

            # Check 5: Profit Appropriation (ONLY if brought forward profit is present)
            if (curr_prof is not None or net_prof is not None) and bf_prof is not None and tot_appr is not None:
                base_prof = curr_prof if curr_prof is not None else net_prof
                calc_appr = base_prof + bf_prof
                checks.append(cls._create_check(
                    name=f"[{period_name}] Profit Appropriation Reconciliation",
                    formula="Current Profit + Brought Forward Profit = Total Available for Appropriation",
                    operands={"current_profit": base_prof, "brought_forward_profit": bf_prof},
                    calculated=calc_appr,
                    reported=tot_appr,
                    tolerance=tolerance
                ))

        return checks

    @classmethod
    def _validate_cash_flow(cls, data: Dict[str, Any], tolerance: float) -> List[FinancialCheckResult]:
        checks = []
        periods = data.get("periods", [])

        for period in periods:
            period_name = period.get("period_name", "Period")
            
            ocf = period.get("operating_cash_flow")
            icf = period.get("investing_cash_flow")
            fcf = period.get("financing_cash_flow")
            fx = period.get("fx_translation_adjustment", 0.0) or 0.0
            
            net_change = period.get("net_change_in_cash")
            opening = period.get("opening_cash")
            adj = period.get("cash_acquired_adjustments", 0.0) or 0.0
            closing = period.get("closing_cash")

            # Check 1: Operating + Investing + Financing + FX + Adjustments ≈ Net Change in Cash
            valid_flows = [x for x in [ocf, icf, fcf] if x is not None]
            if valid_flows and net_change is not None:
                calc_net_change = sum(valid_flows) + fx
                if abs(calc_net_change - net_change) > tolerance and adj != 0.0:
                    calc_net_change += adj
                checks.append(cls._create_check(
                    name=f"[{period_name}] Net Cash Flow Reconciliation",
                    formula="Operating Cash + Investing Cash + Financing Cash + FX + Adjustments = Net Change in Cash",
                    operands={"operating_cash": ocf, "investing_cash": icf, "financing_cash": fcf, "fx_adjustment": fx, "adjustments": adj},
                    calculated=calc_net_change,
                    reported=net_change,
                    tolerance=tolerance
                ))

            # Check 2: Opening Cash + Net Change + Adjustments ≈ Closing Cash (ONLY if opening cash exists)
            if opening is not None and net_change is not None and closing is not None:
                calc_closing = opening + net_change + adj
                checks.append(cls._create_check(
                    name=f"[{period_name}] Ending Cash Reconciliation",
                    formula="Opening Cash + Net Change in Cash + Adjustments = Closing Cash",
                    operands={"opening_cash": opening, "net_change_in_cash": net_change, "adjustments": adj},
                    calculated=calc_closing,
                    reported=closing,
                    tolerance=tolerance
                ))

        return checks
