import { api } from '../api/workspace.js';
import { table } from '../components/common/table.js';
import { empty, heading } from '../components/common/heading.js';
import { status } from '../components/common/status.js';
import { bindForm, notice } from '../hooks/forms.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

export async function modelsPage(profile, account) {
  const [versions, datasets] = await Promise.all([api.models(), api.datasets()]);
  const canTrial = account.role === 'analyst' && datasets.length > 0;
  const form = canTrial ? `<form id="trial-form">
    <label>数据版本<select name="dataset_id">${datasets.map(row =>
      `<option value="${row.id}">${e(row.name)} · ${row.count} 行</option>`).join('')}</select></label>
    <p class="muted">以该版本的训练与校准完工记录拟合候选版本；独立核验记录只用于与在用版比较，不参与训练或校准。试算期间可照常提交新预算。</p>
    <div class="form-error" data-error role="alert"></div>
    <button type="submit">提交候选试算</button></form>` :
    '<p class="muted">分析员可选择数据版本提交候选试算，后台比较达标后自动切换。</p>';
  const busy = versions.some(item => item.state === 'pending' || item.state === 'trialing');
  const columns = [
    { key: 'name', label: '版本' }, { key: 'state', label: '状态' },
    { key: 'fit', label: '拟合/校准' }, { key: 'audit_mae', label: '核验 MAE（分）' },
    { key: 'exceeded', label: '超出预留' }, { key: 'rival', label: '与在用版比较' },
    { key: 'dataset_id', label: '数据版本' }, { key: 'created_at', label: '提交时间' },
  ];
  return {
    html: heading(profile.labels.models, profile.versioning) +
      `<div class="board"><aside class="side"><h2>候选试算</h2>${form}</aside>
      <section class="work"><div class="work-head"><h2>版本记录</h2><button type="button" class="quiet" id="refresh-models">刷新</button></div>
      ${versions.length ? table(columns, versions, (row, column, value) => {
        if (column.key === 'name') return `<strong>${e(value)}</strong>`;
        if (column.key === 'state') return status(value);
        if (column.key === 'fit') return row.train_count === null ? '—' : e(`${row.train_count} / ${row.calibration_count}`);
        if (column.key === 'audit_mae') return value === null ? '—' : e(value);
        if (column.key === 'exceeded') return row.audit_exceeded === null ? '—' : e(`${row.audit_exceeded}/${row.audit_count}`);
        if (column.key === 'rival') {
          if (row.rival) return e(`较 ${row.rival.name}：MAE ${row.audit_mae} 对 ${row.rival.mae}，超出 ${row.audit_exceeded} 对 ${row.rival.exceeded}`);
          return row.error ? e(row.error) : '—';
        }
        if (column.key === 'dataset_id') return `<a href="#datasets/${row.dataset_id}">${shortId(row.dataset_id)}</a>`;
        return e(timeText(value));
      }) : empty('还没有模型版本', '提交首个计算单时会以现有完工记录照原法训练首版，也可以先提交候选试算。')}
      <details class="details"><summary>切换口径</summary><p>${e(profile.versioning)}</p></details></section></div>`,
    mount(root, refresh) {
      root.querySelector('#refresh-models').onclick = refresh;
      bindForm(root, 'trial-form', async data => {
        const submitted = await api.trial(Object.fromEntries(data));
        notice(`已提交候选试算 ${submitted.name}，后台将与在用版比较。`);
        refresh();
      });
    },
    poll: busy,
  };
}
