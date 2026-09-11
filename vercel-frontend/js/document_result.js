document.addEventListener('DOMContentLoaded', () => {
  if (typeof DOCUMENT_NAME !== 'undefined' && DOCUMENT_NAME) {
    fetchDocumentDetails(DOCUMENT_NAME);
  }
});

let currentDocumentData = null;
let primaryChartInstance = null;
let secondaryChartInstance = null;

async function fetchDocumentDetails(name) {
  try {
    const res = await fetch(`https://findoc-ai-2c11.onrender.com/api/v1/documents/${encodeURIComponent(name)}`);
    if (!res.ok) {
      alert('Document record not found in database repository.');
      return;
    }

    const data = await res.json();
    currentDocumentData = data;
    renderDocumentDetails(data);
  } catch (err) {
    console.error('Failed to fetch document details from backend API:', err);
  }
}

function renderDocumentDetails(data) {
  // 1. Meta Summary Header
  const nameEl = document.getElementById('meta-doc-name');
  const typeEl = document.getElementById('meta-doc-type');
  const statusEl = document.getElementById('meta-status');
  const timeEl = document.getElementById('meta-timestamp');
  const speedEl = document.getElementById('meta-speed');

  if (nameEl) nameEl.textContent = data.document_name;
  if (typeEl) {
    typeEl.textContent = formatCategoryName(data.document_type);
    typeEl.className = `badge-status ${data.document_type || 'na'}`;
  }

  const isProcPass = data.processing_status === 'PASS' || data.processing_status === 'COMPLETED';
  if (statusEl) {
    statusEl.className = isProcPass ? 'badge-status pass' : 'badge-status fail';
    statusEl.innerHTML = isProcPass ? '<i class="fa-solid fa-check"></i> PROCESSED' : '<i class="fa-solid fa-xmark"></i> FAILED';
  }

  if (data.processing_metadata) {
    if (timeEl) timeEl.textContent = new Date(data.processing_metadata.processed_at).toLocaleString();
    if (speedEl) speedEl.textContent = `${data.processing_metadata.processing_time_ms} ms (${data.processing_metadata.model_used || 'AI Engine'})`;
  }

  // 2. File Integrity Validation Banner
  renderFileValidation(data.file_validation);

  // 3. Additive Executive Layer: Dynamic KPIs, Charts, Comparative Insights
  renderExecutiveKPIs(data);
  renderExecutiveCharts(data);
  renderComparativeInsights(data);

  // 4. Extracted Fields / Overview Grid (Original Preserved)
  renderExtractedFields(data.extracted_data, data.document_type, data.processing_metadata);

  // 5. Statements & Comparative Table Rendering (Original Preserved)
  renderTables(data.extracted_data, data.document_type);

  // 6. Financial Validation Formula Checks (Original Preserved)
  renderValidationChecks(data.validation);

  // 7. JSON Viewer Payload
  const jsonViewer = document.getElementById('json-viewer-content');
  if (jsonViewer) {
    jsonViewer.textContent = JSON.stringify(data, null, 2);
  }
}

// -------------------------------------------------------------
// ADDITIVE EXECUTIVE LAYER IMPLEMENTATION
// -------------------------------------------------------------

function renderExecutiveKPIs(data) {
  const container = document.getElementById('executive-kpi-container');
  if (!container || !data.extracted_data) return;

  const ext = data.extracted_data;
  const docType = data.document_type;
  const kpis = [];

  const unitStr = ext.unit ? ` (${ext.unit})` : '';
  const currStr = ext.currency ? `${ext.currency} ` : '';

  if (docType === 'invoice') {
    if (ext.total_amount !== null && ext.total_amount !== undefined) {
      kpis.push({ title: 'Total Amount', value: `${currStr}${ext.total_amount.toLocaleString(undefined, {minimumFractionDigits: 2})}`, icon: 'receipt', color: '#10B981' });
    }
    if (ext.subtotal !== null && ext.subtotal !== undefined) {
      kpis.push({ title: 'Subtotal', value: `${currStr}${ext.subtotal.toLocaleString(undefined, {minimumFractionDigits: 2})}`, icon: 'calculator', color: '#3B82F6' });
    }
    if (ext.tax_amount !== null && ext.tax_amount !== undefined) {
      kpis.push({ title: 'Tax Amount', value: `${currStr}${ext.tax_amount.toLocaleString(undefined, {minimumFractionDigits: 2})}`, icon: 'percent', color: '#F59E0B' });
    }
    if (ext.line_items) {
      kpis.push({ title: 'Line Items Count', value: ext.line_items.length, icon: 'list-ol', color: '#8B5CF6' });
    }
  } else if (ext.periods && ext.periods.length > 0) {
    const p0 = ext.periods[0];
    const periodLabel = p0.period_name || 'Current Period';

    if (docType === 'balance_sheet') {
      if (p0.total_assets !== null && p0.total_assets !== undefined) {
        kpis.push({ title: `Total Assets (${periodLabel})`, value: `${currStr}${p0.total_assets.toLocaleString()}${unitStr}`, icon: 'vault', color: '#10B981' });
      }
      if (p0.total_capital_and_liabilities !== null && p0.total_capital_and_liabilities !== undefined) {
        kpis.push({ title: `Capital & Liabilities (${periodLabel})`, value: `${currStr}${p0.total_capital_and_liabilities.toLocaleString()}${unitStr}`, icon: 'building-columns', color: '#3B82F6' });
      }
      if (p0.total_equity !== null && p0.total_equity !== undefined) {
        kpis.push({ title: `Total Equity (${periodLabel})`, value: `${currStr}${p0.total_equity.toLocaleString()}${unitStr}`, icon: 'chart-pie', color: '#8B5CF6' });
      }
      if (ext.periods.length > 1 && p0.total_assets && ext.periods[1].total_assets) {
        const p1 = ext.periods[1];
        const diff = p0.total_assets - p1.total_assets;
        const pct = ((diff / p1.total_assets) * 100).toFixed(2);
        const sign = diff >= 0 ? '+' : '';
        kpis.push({ title: `YoY Asset Growth`, value: `${sign}${pct}%`, icon: 'arrow-trend-up', color: diff >= 0 ? '#10B981' : '#EF4444' });
      }
    } else if (docType === 'profit_and_loss') {
      const inc = p0.total_income || p0.revenue;
      if (inc !== null && inc !== undefined) {
        kpis.push({ title: `Total Income (${periodLabel})`, value: `${currStr}${inc.toLocaleString()}${unitStr}`, icon: 'hand-holding-dollar', color: '#10B981' });
      }
      if (p0.total_expenditure !== null && p0.total_expenditure !== undefined) {
        kpis.push({ title: `Total Expenditure (${periodLabel})`, value: `${currStr}${p0.total_expenditure.toLocaleString()}${unitStr}`, icon: 'money-bill-trend-up', color: '#EF4444' });
      }
      const np = p0.net_profit || p0.net_profit_before_minority_interest;
      if (np !== null && np !== undefined) {
        kpis.push({ title: `Net Profit (${periodLabel})`, value: `${currStr}${np.toLocaleString()}${unitStr}`, icon: 'chart-line', color: np >= 0 ? '#10B981' : '#EF4444' });
      }
      if (inc && np) {
        const margin = ((np / inc) * 100).toFixed(2);
        kpis.push({ title: `Net Profit Margin`, value: `${margin}%`, icon: 'percent', color: '#8B5CF6' });
      }
    } else if (docType === 'cash_flow_statement') {
      if (p0.operating_cash_flow !== null && p0.operating_cash_flow !== undefined) {
        kpis.push({ title: `Operating Cash Flow`, value: `${currStr}${p0.operating_cash_flow.toLocaleString()}${unitStr}`, icon: 'industry', color: p0.operating_cash_flow >= 0 ? '#10B981' : '#EF4444' });
      }
      if (p0.net_change_in_cash !== null && p0.net_change_in_cash !== undefined) {
        kpis.push({ title: `Net Cash Change`, value: `${currStr}${p0.net_change_in_cash.toLocaleString()}${unitStr}`, icon: 'arrows-rotate', color: p0.net_change_in_cash >= 0 ? '#10B981' : '#EF4444' });
      }
      if (p0.closing_cash !== null && p0.closing_cash !== undefined) {
        kpis.push({ title: `Closing Cash Balance`, value: `${currStr}${p0.closing_cash.toLocaleString()}${unitStr}`, icon: 'piggy-bank', color: '#3B82F6' });
      }
    }
  }

  if (kpis.length === 0) {
    container.innerHTML = '';
    return;
  }

  const kpiCardsHtml = kpis.map(k => `
    <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 18px 20px; box-shadow: var(--shadow-xs); display: flex; align-items: center; gap: 16px;">
      <div style="width: 46px; height: 46px; border-radius: 12px; background: rgba(0,0,0,0.04); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; color: ${k.color};">
        <i class="fa-solid fa-${k.icon}"></i>
      </div>
      <div>
        <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-subtle); text-transform: uppercase; letter-spacing: 0.04em;">${escapeHtml(k.title)}</div>
        <div style="font-size: 1.2rem; font-weight: 800; color: var(--text-main); margin-top: 2px;">${k.value}</div>
      </div>
    </div>
  `).join('');

  container.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px;">
      ${kpiCardsHtml}
    </div>
  `;
}

function formatCompactAxis(val, currency = '') {
  if (val === null || val === undefined || isNaN(val)) return '0';
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  const isINR = currency === 'INR' || currency === 'â‚¹';

  if (isINR) {
    if (abs >= 1e7) return `${sign}â‚¹${(abs / 1e7).toFixed(1)} Cr`;
    if (abs >= 1e5) return `${sign}â‚¹${(abs / 1e5).toFixed(1)} L`;
    if (abs >= 1e3) return `${sign}â‚¹${(abs / 1e3).toFixed(0)}k`;
    return `${sign}â‚¹${abs}`;
  }
  if (abs >= 1e9) return `${sign}${currency ? currency + ' ' : ''}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${currency ? currency + ' ' : ''}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${currency ? currency + ' ' : ''}${(abs / 1e3).toFixed(0)}k`;
  return `${sign}${currency ? currency + ' ' : ''}${abs}`;
}

function formatFullCurrencyValue(val, currency = '', unit = '') {
  if (val === null || val === undefined || isNaN(val)) return '-';
  const prefix = currency ? `${currency} ` : '';
  const suffix = unit ? ` (${unit})` : '';
  return `${prefix}${Number(val).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}${suffix}`;
}

function renderExecutiveCharts(data) {
  const container = document.getElementById('executive-charts-container');
  if (!container || !data.extracted_data || typeof Chart === 'undefined') return;

  const ext = data.extracted_data;
  const docType = data.document_type;
  const curr = ext.currency || '';
  const unit = ext.unit || '';

  if (docType === 'invoice') {
    const rawItems = ext.line_items || [];
    // Eliminate missing/empty bars by filtering strictly for valid positive totals
    const validItems = rawItems
      .filter(it => it && typeof it.line_total === 'number' && it.line_total > 0)
      .sort((a, b) => (b.line_total || 0) - (a.line_total || 0));

    if (validItems.length === 0 && !ext.total_amount) {
      container.innerHTML = '';
      return;
    }

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 8px;">
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
            <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
              <i class="fa-solid fa-chart-bar" style="color: #6366F1; margin-right: 6px;"></i>Item Value Distribution
            </h4>
            <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-subtle); background: rgba(99, 102, 241, 0.1); padding: 2px 8px; border-radius: 6px;">
              ${validItems.length} active items
            </span>
          </div>
          <div style="height: 240px; position: relative;">
            <canvas id="chart-primary"></canvas>
          </div>
        </div>

        <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
            <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
              <i class="fa-solid fa-chart-pie" style="color: #10B981; margin-right: 6px;"></i>Financial Cost Composition
            </h4>
            <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-subtle);">
              ${ext.total_amount ? formatFullCurrencyValue(ext.total_amount, curr) : ''}
            </span>
          </div>
          <div style="height: 240px; position: relative;">
            <canvas id="chart-secondary"></canvas>
          </div>
        </div>
      </div>
    `;

    setTimeout(() => {
      const ctx1 = document.getElementById('chart-primary')?.getContext('2d');
      const ctx2 = document.getElementById('chart-secondary')?.getContext('2d');
      if (primaryChartInstance) primaryChartInstance.destroy();
      if (secondaryChartInstance) secondaryChartInstance.destroy();

      // Chart 1: Bar Chart (Top Items cleanly displayed without missing bars)
      if (ctx1 && validItems.length > 0) {
        let displayItems = validItems;
        if (validItems.length > 7) {
          const top6 = validItems.slice(0, 6);
          const othersTotal = validItems.slice(6).reduce((acc, it) => acc + (it.line_total || 0), 0);
          displayItems = [...top6, { description: `Other Items (${validItems.length - 6})`, line_total: othersTotal }];
        }

        const labels = displayItems.map(it => {
          const d = it.description || 'Item';
          return d.length > 20 ? d.slice(0, 18) + '...' : d;
        });
        const fullLabels = displayItems.map(it => it.description || 'Item');
        const totals = displayItems.map(it => it.line_total || 0);

        primaryChartInstance = new Chart(ctx1, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Amount',
              data: totals,
              backgroundColor: '#6366F1',
              borderRadius: 6,
              borderSkipped: false,
              maxBarThickness: 36
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  title: (items) => items.length ? fullLabels[items[0].dataIndex] : '',
                  label: (ctx) => ` Amount: ${formatFullCurrencyValue(ctx.raw, curr)}`
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: {
                  font: { size: 11, family: 'Inter, sans-serif' },
                  maxRotation: 25,
                  minRotation: 0
                }
              },
              y: {
                grid: { color: 'rgba(148, 163, 184, 0.12)' },
                ticks: {
                  font: { size: 10, family: 'Inter, sans-serif' },
                  callback: (val) => formatCompactAxis(val, curr)
                }
              }
            }
          }
        });
      }

      // Chart 2: Doughnut Composition (Subtotal, Taxes, Discounts)
      if (ctx2) {
        let compLabels = [];
        let compData = [];
        let compColors = [];

        const subtotal = ext.subtotal || 0;
        const tax = ext.tax_amount || 0;
        const discount = ext.discount_amount || 0;

        if (subtotal > 0 || tax > 0) {
          if (subtotal > 0) {
            compLabels.push('Subtotal / Taxable');
            compData.push(subtotal);
            compColors.push('#3B82F6');
          }
          if (tax > 0) {
            compLabels.push('Tax / Duties');
            compData.push(tax);
            compColors.push('#F59E0B');
          }
          if (discount > 0) {
            compLabels.push('Discount Savings');
            compData.push(discount);
            compColors.push('#EC4899');
          }
        } else if (validItems.length > 0) {
          // Fallback to top items share
          const top4 = validItems.slice(0, 4);
          top4.forEach((it, idx) => {
            compLabels.push((it.description || `Item ${idx+1}`).slice(0, 16));
            compData.push(it.line_total);
          });
          compColors = ['#6366F1', '#10B981', '#F59E0B', '#3B82F6'];
        }

        if (compData.length > 0) {
          secondaryChartInstance = new Chart(ctx2, {
            type: 'doughnut',
            data: {
              labels: compLabels,
              datasets: [{
                data: compData,
                backgroundColor: compColors,
                borderWidth: 2,
                borderColor: '#ffffff'
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              cutout: '68%',
              plugins: {
                legend: {
                  position: 'bottom',
                  labels: {
                    boxWidth: 10,
                    usePointStyle: true,
                    font: { size: 11, family: 'Inter, sans-serif' }
                  }
                },
                tooltip: {
                  callbacks: {
                    label: (ctx) => ` ${ctx.label}: ${formatFullCurrencyValue(ctx.raw, curr)}`
                  }
                }
              }
            }
          });
        }
      }
    }, 100);

  } else if (ext.periods && ext.periods.length > 0) {
    const periods = ext.periods;
    const periodLabels = periods.map(p => p.period_name || 'Period');

    if (docType === 'profit_and_loss') {
      container.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 8px;">
          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-chart-column" style="color: #10B981; margin-right: 6px;"></i>Comparative Income vs Expenditure
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Multi-Period Comparison</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-primary"></canvas>
            </div>
          </div>

          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-arrow-trend-up" style="color: #0EA5E9; margin-right: 6px;"></i>Net Profit Performance Trend
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Bottom-Line Dynamics</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-secondary"></canvas>
            </div>
          </div>
        </div>
      `;

      setTimeout(() => {
        const ctx1 = document.getElementById('chart-primary')?.getContext('2d');
        const ctx2 = document.getElementById('chart-secondary')?.getContext('2d');
        if (!ctx1 || !ctx2) return;

        if (primaryChartInstance) primaryChartInstance.destroy();
        if (secondaryChartInstance) secondaryChartInstance.destroy();

        // Robust data extraction with fallbacks to avoid missing bars
        const labels = periodLabels.slice().reverse();
        const incomes = periods.map(p => p.total_income ?? (p.revenue ?? ((p.interest_earned || 0) + (p.other_income || 0)) ?? 0)).slice().reverse();
        const exps = periods.map(p => p.total_expenditure ?? ((p.interest_expended || 0) + (p.operating_expenses || 0) + (p.provisions_and_contingencies || 0)) ?? 0).slice().reverse();
        const netProfits = periods.map(p => p.net_profit ?? (p.net_profit_before_minority_interest ?? ((p.total_income || 0) - (p.total_expenditure || 0)))).slice().reverse();

        // Chart 1: Grouped Bar (Income vs Expenditure)
        primaryChartInstance = new Chart(ctx1, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Total Income',
                data: incomes,
                backgroundColor: '#10B981',
                borderRadius: 6,
                borderSkipped: false,
                maxBarThickness: 42
              },
              {
                label: 'Total Expenditure',
                data: exps,
                backgroundColor: '#F43F5E',
                borderRadius: 6,
                borderSkipped: false,
                maxBarThickness: 42
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'top',
                labels: {
                  boxWidth: 12,
                  usePointStyle: true,
                  font: { size: 11, family: 'Inter, sans-serif' }
                }
              },
              tooltip: {
                callbacks: {
                  label: (ctx) => ` ${ctx.dataset.label}: ${formatFullCurrencyValue(ctx.raw, curr, unit)}`
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { font: { size: 11, family: 'Inter, sans-serif' } }
              },
              y: {
                grid: { color: 'rgba(148, 163, 184, 0.12)' },
                ticks: {
                  font: { size: 10, family: 'Inter, sans-serif' },
                  callback: (val) => formatCompactAxis(val, curr)
                }
              }
            }
          }
        });

        // Chart 2: Net Profit Trend Line
        secondaryChartInstance = new Chart(ctx2, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Net Profit',
              data: netProfits,
              borderColor: '#0EA5E9',
              backgroundColor: 'rgba(14, 165, 233, 0.14)',
              borderWidth: 3,
              fill: true,
              tension: 0.32,
              pointRadius: 6,
              pointHoverRadius: 8,
              pointBackgroundColor: '#0EA5E9',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'top',
                labels: {
                  boxWidth: 12,
                  usePointStyle: true,
                  font: { size: 11, family: 'Inter, sans-serif' }
                }
              },
              tooltip: {
                callbacks: {
                  label: (ctx) => ` Net Profit: ${formatFullCurrencyValue(ctx.raw, curr, unit)}`
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { font: { size: 11, family: 'Inter, sans-serif' } }
              },
              y: {
                grid: { color: 'rgba(148, 163, 184, 0.12)' },
                ticks: {
                  font: { size: 10, family: 'Inter, sans-serif' },
                  callback: (val) => formatCompactAxis(val, curr)
                }
              }
            }
          }
        });
      }, 100);

    } else if (docType === 'balance_sheet') {
      container.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 8px;">
          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-scale-balanced" style="color: #10B981; margin-right: 6px;"></i>Balance Sheet Structural Reconciliation
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Assets vs Liabilities</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-primary"></canvas>
            </div>
          </div>

          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-vault" style="color: #8B5CF6; margin-right: 6px;"></i>Total Equity & Net Worth
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Capital Growth</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-secondary"></canvas>
            </div>
          </div>
        </div>
      `;

      setTimeout(() => {
        const ctx1 = document.getElementById('chart-primary')?.getContext('2d');
        const ctx2 = document.getElementById('chart-secondary')?.getContext('2d');
        if (!ctx1 || !ctx2) return;

        if (primaryChartInstance) primaryChartInstance.destroy();
        if (secondaryChartInstance) secondaryChartInstance.destroy();

        const labels = periodLabels.slice().reverse();
        const assets = periods.map(p => p.total_assets || 0).slice().reverse();
        const capLiab = periods.map(p => p.total_capital_and_liabilities || 0).slice().reverse();
        const equity = periods.map(p => p.total_equity || p.capital_and_reserves || 0).slice().reverse();

        primaryChartInstance = new Chart(ctx1, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [
              { label: 'Total Assets', data: assets, backgroundColor: '#10B981', borderRadius: 6, maxBarThickness: 42 },
              { label: 'Capital & Liabilities', data: capLiab, backgroundColor: '#3B82F6', borderRadius: 6, maxBarThickness: 42 }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { boxWidth: 12, usePointStyle: true } },
              tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${formatFullCurrencyValue(ctx.raw, curr, unit)}` } }
            },
            scales: {
              x: { grid: { display: false } },
              y: { grid: { color: 'rgba(148, 163, 184, 0.12)' }, ticks: { callback: (val) => formatCompactAxis(val, curr) } }
            }
          }
        });

        secondaryChartInstance = new Chart(ctx2, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Total Equity',
              data: equity,
              borderColor: '#8B5CF6',
              backgroundColor: 'rgba(139, 92, 246, 0.12)',
              borderWidth: 3,
              fill: true,
              tension: 0.32,
              pointRadius: 6,
              pointBackgroundColor: '#8B5CF6',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { boxWidth: 12, usePointStyle: true } },
              tooltip: { callbacks: { label: (ctx) => ` Total Equity: ${formatFullCurrencyValue(ctx.raw, curr, unit)}` } }
            },
            scales: {
              x: { grid: { display: false } },
              y: { grid: { color: 'rgba(148, 163, 184, 0.12)' }, ticks: { callback: (val) => formatCompactAxis(val, curr) } }
            }
          }
        });
      }, 100);

    } else if (docType === 'cash_flow_statement') {
      container.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-top: 8px;">
          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-water" style="color: #0EA5E9; margin-right: 6px;"></i>Cash Flow Dynamics
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Operating, Investing & Financing</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-primary"></canvas>
            </div>
          </div>

          <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
              <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin: 0;">
                <i class="fa-solid fa-piggy-bank" style="color: #10B981; margin-right: 6px;"></i>Closing Cash Position
              </h4>
              <span style="font-size: 0.75rem; color: var(--text-subtle); font-weight: 600;">Liquidity Trend</span>
            </div>
            <div style="height: 240px; position: relative;">
              <canvas id="chart-secondary"></canvas>
            </div>
          </div>
        </div>
      `;

      setTimeout(() => {
        const ctx1 = document.getElementById('chart-primary')?.getContext('2d');
        const ctx2 = document.getElementById('chart-secondary')?.getContext('2d');
        if (!ctx1 || !ctx2) return;

        if (primaryChartInstance) primaryChartInstance.destroy();
        if (secondaryChartInstance) secondaryChartInstance.destroy();

        const labels = periodLabels.slice().reverse();
        const ocf = periods.map(p => p.operating_cash_flow || 0).slice().reverse();
        const icf = periods.map(p => p.investing_cash_flow || 0).slice().reverse();
        const fcf = periods.map(p => p.financing_cash_flow || 0).slice().reverse();
        const closing = periods.map(p => p.closing_cash || 0).slice().reverse();

        primaryChartInstance = new Chart(ctx1, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [
              { label: 'Operating CF', data: ocf, backgroundColor: '#10B981', borderRadius: 4 },
              { label: 'Investing CF', data: icf, backgroundColor: '#F59E0B', borderRadius: 4 },
              { label: 'Financing CF', data: fcf, backgroundColor: '#6366F1', borderRadius: 4 }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { boxWidth: 10, usePointStyle: true } },
              tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${formatFullCurrencyValue(ctx.raw, curr, unit)}` } }
            },
            scales: {
              x: { grid: { display: false } },
              y: { grid: { color: 'rgba(148, 163, 184, 0.12)' }, ticks: { callback: (val) => formatCompactAxis(val, curr) } }
            }
          }
        });

        secondaryChartInstance = new Chart(ctx2, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Closing Cash',
              data: closing,
              borderColor: '#10B981',
              backgroundColor: 'rgba(16, 185, 129, 0.12)',
              borderWidth: 3,
              fill: true,
              tension: 0.32,
              pointRadius: 6,
              pointBackgroundColor: '#10B981',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { boxWidth: 10, usePointStyle: true } },
              tooltip: { callbacks: { label: (ctx) => ` Closing Cash: ${formatFullCurrencyValue(ctx.raw, curr, unit)}` } }
            },
            scales: {
              x: { grid: { display: false } },
              y: { grid: { color: 'rgba(148, 163, 184, 0.12)' }, ticks: { callback: (val) => formatCompactAxis(val, curr) } }
            }
          }
        });
      }, 100);
    }
  }
}

function renderComparativeInsights(data) {
  const container = document.getElementById('comparative-insights-container');
  if (!container || !data.extracted_data || !data.extracted_data.periods || data.extracted_data.periods.length < 2) {
    if (container) container.innerHTML = '';
    return;
  }

  const periods = data.extracted_data.periods;
  const p0 = periods[0];
  const p1 = periods[1];

  const keysToCompare = [
    { key: 'total_assets', label: 'Total Assets' },
    { key: 'total_capital_and_liabilities', label: 'Total Capital & Liabilities' },
    { key: 'total_income', label: 'Total Income' },
    { key: 'total_expenditure', label: 'Total Expenditure' },
    { key: 'net_profit', label: 'Net Profit' },
    { key: 'operating_cash_flow', label: 'Operating Cash Flow' }
  ];

  const rows = [];
  keysToCompare.forEach(item => {
    const v0 = p0[item.key];
    const v1 = p1[item.key];

    if (v0 !== null && v0 !== undefined && v1 !== null && v1 !== undefined) {
      const diff = v0 - v1;
      const pct = v1 !== 0 ? ((diff / Math.abs(v1)) * 100).toFixed(2) : 'N/A';
      const pctBadge = diff >= 0
        ? `<span style="color: #10B981; font-weight: 700;"><i class="fa-solid fa-arrow-up me-1"></i>+${pct}%</span>`
        : `<span style="color: #EF4444; font-weight: 700;"><i class="fa-solid fa-arrow-down me-1"></i>${pct}%</span>`;

      rows.push(`
        <tr>
          <td style="font-weight: 700;">${escapeHtml(item.label)}</td>
          <td>${v0.toLocaleString()}</td>
          <td>${v1.toLocaleString()}</td>
          <td style="font-weight: 700;">${diff >= 0 ? '+' : ''}${diff.toLocaleString()}</td>
          <td>${pctBadge}</td>
        </tr>
      `);
    }
  });

  if (rows.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-xl); padding: 20px; box-shadow: var(--shadow-xs); margin-top: 8px;">
      <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
        <i class="fa-solid fa-arrow-trend-up" style="color: var(--primary);"></i>
        Comparative Period Variance Analysis (${p0.period_name} vs ${p1.period_name})
      </h4>
      <table class="custom-table">
        <thead>
          <tr>
            <th>Key Metric</th>
            <th>${escapeHtml(p0.period_name)}</th>
            <th>${escapeHtml(p1.period_name)}</th>
            <th>Absolute Variance</th>
            <th>YoY Change %</th>
          </tr>
        </thead>
        <tbody>
          ${rows.join('')}
        </tbody>
      </table>
    </div>
  `;
}

// -------------------------------------------------------------
// ORIGINAL DISPLAY UI FUNCTIONS (PRESERVED)
// -------------------------------------------------------------

function renderFileValidation(fval) {
  const container = document.getElementById('file-validation-container');
  if (!container || !fval) return;

  const isPass = fval.status === 'PASS';
  const badge = isPass ? '<span class="badge-status pass">PASS</span>' : '<span class="badge-status fail">FAILED</span>';

  container.innerHTML = `
    <div><strong>File Type:</strong> ${escapeHtml(fval.file_type || 'Unknown').toUpperCase()}</div>
    <div><strong>Format Valid:</strong> ${fval.is_supported ? 'Yes' : 'No'}</div>
    <div><strong>Page Count:</strong> ${fval.page_count || 1} (Limit: 3)</div>
    <div><strong>Integrity Check:</strong> ${badge}</div>
  `;
}

function renderExtractedFields(ext, docType, metadata) {
  const grid = document.getElementById('extracted-fields-grid');
  if (!grid) return;

  if (!ext) {
    grid.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No extracted schema data available.</div>';
    return;
  }

  const fieldCards = [];

  if (ext.company_name) {
    fieldCards.push(createFieldCard('Company Name', ext.company_name, 'building', ext.evidence ? ext.evidence['company_name'] : null));
  }
  if (ext.vendor_name) {
    fieldCards.push(createFieldCard('Vendor Name', ext.vendor_name, 'store', ext.evidence ? ext.evidence['vendor_name'] : null));
  }
  if (ext.customer_name) {
    fieldCards.push(createFieldCard('Customer Name', ext.customer_name, 'user', ext.evidence ? ext.evidence['customer_name'] : null));
  }
  if (ext.document_title) {
    fieldCards.push(createFieldCard('Document Title', ext.document_title, 'file-lines', ext.evidence ? ext.evidence['document_title'] : null));
  }
  if (ext.invoice_number) {
    fieldCards.push(createFieldCard('Invoice Number', ext.invoice_number, 'receipt', ext.evidence ? ext.evidence['invoice_number'] : null));
  }
  if (ext.invoice_date) {
    fieldCards.push(createFieldCard('Invoice Date', ext.invoice_date, 'calendar-days', ext.evidence ? ext.evidence['invoice_date'] : null));
  }
  if (ext.reporting_date) {
    fieldCards.push(createFieldCard('Reporting Date', ext.reporting_date, 'calendar', ext.evidence ? ext.evidence['reporting_date'] : null));
  }
  if (ext.currency || ext.unit) {
    const scaleUnit = [ext.currency, ext.unit ? `(in ${ext.unit})` : ''].filter(Boolean).join(' ');
    fieldCards.push(createFieldCard('Currency & Scale', scaleUnit, 'coins', null));
  }
  if (metadata && metadata.model_used) {
    fieldCards.push(createFieldCard('Processing Engine', metadata.model_used, 'robot', null));
  }

  for (const [key, val] of Object.entries(ext)) {
    if (['line_items', 'periods', 'additional_disclosures', 'evidence', 'company_name', 'vendor_name', 'customer_name', 'invoice_number', 'invoice_date', 'document_title', 'reporting_date', 'currency', 'unit'].includes(key) || key.startsWith('_')) continue;
    if (val === null || val === undefined) continue;

    let displayVal = val;
    if (typeof val === 'number') {
      displayVal = val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      if (ext.unit) displayVal += ` ${ext.unit}`;
    } else {
      displayVal = escapeHtml(String(val));
    }

    let iconName = 'calculator';
    if (key.includes('phone')) iconName = 'phone';
    else if (key.includes('email')) iconName = 'envelope';
    else if (key.includes('address')) iconName = 'location-dot';
    else if (key.includes('tax')) iconName = 'percent';
    else if (key.includes('amount') || key.includes('total') || key.includes('subtotal')) iconName = 'receipt';

    const ev = ext.evidence && ext.evidence[key] ? ext.evidence[key] : null;
    fieldCards.push(createFieldCard(key.replace(/_/g, ' '), displayVal, iconName, ev));
  }

  grid.innerHTML = fieldCards.join('');
}

function createFieldCard(label, value, icon, evidenceObj) {
  let evidenceQuote = '';
  if (evidenceObj && evidenceObj.source_text) {
    evidenceQuote = `
      <div class="evidence-quote" style="margin-top: 6px; font-size: 0.75rem; color: var(--text-muted); background: rgba(0,0,0,0.03); padding: 4px 8px; border-radius: 4px;">
        <i class="fa-solid fa-quote-left me-1"></i>"${escapeHtml(evidenceObj.source_text)}" <span style="opacity: 0.7;">(Pg ${evidenceObj.page_number || 1})</span>
      </div>
    `;
  }

  return `
    <div style="background: var(--bg-app); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 14px;">
      <div style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: var(--text-subtle); letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;">
        <i class="fa-solid fa-${icon}" style="color: var(--primary);"></i>
        ${escapeHtml(label)}
      </div>
      <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-main); margin-top: 6px;">
        ${escapeHtml(String(value))}
      </div>
      ${evidenceQuote}
    </div>
  `;
}

function renderTables(ext, docType) {
  const container = document.getElementById('tables-container');
  if (!container) return;

  if (!ext) {
    container.innerHTML = '<div style="padding: 20px; color: var(--text-muted);">No statement tables available.</div>';
    return;
  }

  // Invoice Line Items
  if (docType === 'invoice' && ext.line_items && ext.line_items.length > 0) {
    const hasDiscount = ext.line_items.some(it => it.discount_percentage !== undefined && it.discount_percentage !== null && Number(it.discount_percentage) > 0);
    const rows = ext.line_items.map(item => {
      const discText = (item.discount_percentage !== undefined && item.discount_percentage !== null && Number(item.discount_percentage) > 0) 
        ? `${item.discount_percentage}%` 
        : '-';
      const unitPriceStr = (item.unit_price !== null && item.unit_price !== undefined)
        ? (typeof item.unit_price === 'number' ? item.unit_price.toFixed(2) : item.unit_price)
        : '-';
      const lineTotalStr = (item.line_total !== null && item.line_total !== undefined)
        ? (typeof item.line_total === 'number' ? item.line_total.toFixed(2) : item.line_total)
        : '-';
      return `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(item.description || 'Item')}</td>
        <td>${item.quantity !== null && item.quantity !== undefined ? item.quantity : '-'}</td>
        <td>${unitPriceStr}</td>
        ${hasDiscount ? `<td>${discText}</td>` : ''}
        <td style="font-weight: 700;">${lineTotalStr}</td>
      </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table class="custom-table">
        <thead>
          <tr>
            <th>Item Description</th>
            <th>Quantity</th>
            <th>Unit Price</th>
            ${hasDiscount ? `<th>Disc %</th>` : ''}
            <th>Line Total</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    return;
  }

  // Balance Sheet / Profit & Loss / Cash Flow Comparative Tables
  if (ext.periods && ext.periods.length > 0) {
    const periods = ext.periods;
    const periodHeaders = periods.map(p => p.period_name || 'Period');

    let tablesHtml = '';

    const hasStructuredBS = periods.some(p => (p.liability_equity_line_items && p.liability_equity_line_items.length > 0) || (p.asset_line_items && p.asset_line_items.length > 0));

    if (hasStructuredBS) {
      // 1. CAPITAL AND LIABILITIES TABLE
      tablesHtml += `
        <div style="margin-bottom: 24px;">
          <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <i class="fa-solid fa-building-columns" style="color: var(--primary);"></i>
            CAPITAL AND LIABILITIES
          </h4>
          <table class="custom-table">
            <thead>
              <tr>
                <th>Line Item</th>
                <th style="width: 100px;">Schedule</th>
                ${periodHeaders.map(h => `<th style="text-align: right;">${escapeHtml(h)}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${renderBSSectionRows(periods, 'liability_equity_line_items', 'total_capital_and_liabilities')}
            </tbody>
          </table>
        </div>
      `;

      // 2. ASSETS TABLE
      tablesHtml += `
        <div style="margin-bottom: 24px;">
          <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <i class="fa-solid fa-vault" style="color: var(--primary);"></i>
            ASSETS
          </h4>
          <table class="custom-table">
            <thead>
              <tr>
                <th>Line Item</th>
                <th style="width: 100px;">Schedule</th>
                ${periodHeaders.map(h => `<th style="text-align: right;">${escapeHtml(h)}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${renderBSSectionRows(periods, 'asset_line_items', 'total_assets')}
            </tbody>
          </table>
        </div>
      `;
    } else {
      const allLineItemsMap = new Map();

      periods.forEach(p => {
        const items = p.line_items || p.asset_line_items || p.liability_equity_line_items || [];
        items.forEach(it => {
          if (!allLineItemsMap.has(it.line_item_name)) {
            allLineItemsMap.set(it.line_item_name, { label: it.line_item_name, schedule: it.schedule || '-' });
          }
        });
      });

      const totalKeys = ['total_assets', 'total_capital_and_liabilities', 'revenue', 'gross_profit', 'total_income', 'total_expenditure', 'net_profit', 'operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow', 'closing_cash'];
      totalKeys.forEach(key => {
        if (periods.some(p => p[key] !== null && p[key] !== undefined)) {
          allLineItemsMap.set(key, { label: key.replace(/_/g, ' ').toUpperCase(), schedule: 'TOTAL', isTotal: true });
        }
      });

      const rows = Array.from(allLineItemsMap.entries()).map(([key, info]) => {
        const colVals = periods.map(p => {
          let val = null;
          if (info.isTotal) {
            val = p[key];
          } else {
            const items = p.line_items || p.asset_line_items || p.liability_equity_line_items || [];
            const found = items.find(i => i.line_item_name === key);
            val = found ? found.amount : null;
          }
          if (val === null || val === undefined) return '-';
          return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        });

        const rowStyle = info.isTotal ? 'font-weight: 800; background: rgba(0,0,0,0.02);' : '';
        return `
          <tr style="${rowStyle}">
            <td style="font-weight: ${info.isTotal ? '800' : '600'};">${escapeHtml(info.label)}</td>
            <td>${escapeHtml(info.schedule || '-')}</td>
            ${colVals.map(v => `<td style="text-align: right; font-weight: 700;">${v}</td>`).join('')}
          </tr>
        `;
      }).join('');

      tablesHtml += `
        <table class="custom-table">
          <thead>
            <tr>
              <th>Financial Statement Line Item</th>
              <th style="width: 100px;">Schedule</th>
              ${periodHeaders.map(name => `<th style="text-align: right;">${escapeHtml(name)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    // 3. ADDITIONAL DISCLOSURES TABLE
    if (ext.additional_disclosures && ext.additional_disclosures.length > 0) {
      const discRows = ext.additional_disclosures.map(disc => {
        const colVals = periodHeaders.map(pH => {
          const val = (disc.values && disc.values[pH]) !== undefined ? disc.values[pH] : disc.amount;
          if (val === null || val === undefined) return '-';
          return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        });

        return `
          <tr>
            <td style="font-weight: 600;">${escapeHtml(disc.label)}</td>
            <td>${escapeHtml(disc.schedule || '-')}</td>
            ${colVals.map(v => `<td style="text-align: right; font-weight: 700;">${v}</td>`).join('')}
          </tr>
        `;
      }).join('');

      tablesHtml += `
        <div style="margin-top: 24px;">
          <h4 style="font-size: 0.92rem; font-weight: 800; color: var(--text-main); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <i class="fa-solid fa-file-circle-exclamation" style="color: var(--primary);"></i>
            ADDITIONAL DISCLOSURES & CONTINGENT ITEMS
          </h4>
          <table class="custom-table">
            <thead>
              <tr>
                <th>Disclosure Label</th>
                <th style="width: 100px;">Schedule</th>
                ${periodHeaders.map(h => `<th style="text-align: right;">${escapeHtml(h)}</th>`).join('')}
              </tr>
            </thead>
            <tbody>${discRows}</tbody>
          </table>
        </div>
      `;
    }

    container.innerHTML = tablesHtml;
  } else {
    container.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">No line items or comparative period tables extracted.</div>';
  }
}

function renderBSSectionRows(periods, itemKey, totalKey) {
  const itemMap = new Map();

  periods.forEach(p => {
    const items = p[itemKey] || [];
    items.forEach(it => {
      if (!itemMap.has(it.line_item_name)) {
        itemMap.set(it.line_item_name, { label: it.line_item_name, schedule: it.schedule || '-' });
      }
    });
  });

  const periodHeaders = periods.map(p => p.period_name || 'Period');

  const rows = Array.from(itemMap.entries()).map(([name, info]) => {
    const colVals = periods.map(p => {
      const items = p[itemKey] || [];
      const found = items.find(i => i.line_item_name === name);
      if (!found || found.amount === null || found.amount === undefined) return '-';
      return found.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    });

    return `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(name)}</td>
        <td>${escapeHtml(info.schedule || '-')}</td>
        ${colVals.map(v => `<td style="text-align: right; font-weight: 700;">${v}</td>`).join('')}
      </tr>
    `;
  });

  const totalVals = periods.map(p => {
    const tot = p[totalKey];
    if (tot === null || tot === undefined) return '-';
    return tot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  });

  rows.push(`
    <tr style="font-weight: 800; background: rgba(0,0,0,0.03);">
      <td style="font-weight: 800; text-transform: uppercase;">Total</td>
      <td>-</td>
      ${totalVals.map(v => `<td style="text-align: right; font-weight: 800; color: var(--primary);">${v}</td>`).join('')}
    </tr>
  `);

  return rows.join('');
}

function renderValidationChecks(valSummary) {
  const tbody = document.getElementById('validation-checks-table-body');
  const chip = document.getElementById('overall-validation-chip');

  if (!valSummary) return;

  if (chip) {
    const overall = valSummary.overall_status || 'NOT_APPLICABLE';
    chip.textContent = `Financial Validation: ${overall}`;
    chip.className = `badge-status ${overall === 'PASS' ? 'pass' : (overall === 'FAIL' ? 'fail' : 'na')}`;
  }

  const checks = valSummary.checks || [];
  if (!tbody) return;

  if (checks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-muted);">No financial formula checks evaluated for this document.</td></tr>';
    return;
  }

  tbody.innerHTML = checks.map(c => {
    const statusBadge = c.status === 'PASS'
      ? '<span class="badge-status pass"><i class="fa-solid fa-check"></i> PASS</span>'
      : (c.status === 'FAIL'
          ? '<span class="badge-status fail"><i class="fa-solid fa-xmark"></i> FAIL</span>'
          : '<span class="badge-status na">NOT_APPLICABLE</span>');

    const operandsStr = c.operands ? Object.entries(c.operands).map(([k, v]) => `${k}: ${v !== null && v !== undefined ? v : 'null'}`).join(', ') : '-';
    const calcStr = c.calculated_value !== null && c.calculated_value !== undefined ? c.calculated_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-';
    const repStr = c.reported_value !== null && c.reported_value !== undefined ? c.reported_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-';

    return `
      <tr>
        <td style="font-weight: 700;">${escapeHtml(c.name)}</td>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--primary);">${escapeHtml(c.formula)}</td>
        <td style="font-size: 0.78rem; color: var(--text-muted);">${escapeHtml(operandsStr)}</td>
        <td style="font-weight: 700;">${calcStr}</td>
        <td style="font-weight: 700;">${repStr}</td>
        <td style="font-size: 0.8rem; color: var(--text-muted);">${c.variance !== null && c.variance !== undefined ? c.variance.toFixed(2) : 'N/A'}</td>
        <td>${statusBadge}</td>
      </tr>
    `;
  }).join('');
}

function switchInspectionTab(tabId, btnElement) {
  document.querySelectorAll('.tab-pane').forEach(pane => pane.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

  const targetPane = document.getElementById(`tab-${tabId}`);
  if (targetPane) targetPane.style.display = 'block';
  if (btnElement) btnElement.classList.add('active');
}

function copyJsonToClipboard() {
  if (!currentDocumentData) return;

  const str = JSON.stringify(currentDocumentData, null, 2);
  navigator.clipboard.writeText(str).then(() => {
    alert('API JSON payload copied to clipboard!');
  }).catch(err => {
    console.error('Failed to copy JSON:', err);
  });
}

function formatCategoryName(type) {
  switch (type) {
    case 'invoice': return 'Invoice';
    case 'balance_sheet': return 'Balance Sheet';
    case 'profit_and_loss': return 'Profit & Loss';
    case 'cash_flow_statement': return 'Cash Flow';
    case 'unknown': return 'Unknown / Unclassified';
    default: return type || 'Document';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
}

