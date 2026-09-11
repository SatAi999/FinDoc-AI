from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum

class CheckStatusEnum(str, Enum):
    PASS = 'PASS'
    FAIL = 'FAIL'
    NOT_APPLICABLE = 'NOT_APPLICABLE'

class FinancialCheckResult(BaseModel):
    name: str
    formula: str
    operands: Dict[str, Optional[float]] = Field(default_factory=dict)
    calculated_value: Optional[float] = None
    reported_value: Optional[float] = None
    variance: Optional[float] = None
    tolerance: Optional[float] = 0.05
    status: CheckStatusEnum
    explanation: Optional[str] = None

class ValidationSummarySchema(BaseModel):
    checks: List[FinancialCheckResult] = Field(default_factory=list)
    overall_status: CheckStatusEnum = CheckStatusEnum.NOT_APPLICABLE
    issues: List[str] = Field(default_factory=list)
