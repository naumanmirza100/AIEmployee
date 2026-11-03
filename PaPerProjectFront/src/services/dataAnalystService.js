import { companyApi } from './companyAuthService';

/**
 * AI Data Analyst (backend: data_analyst_agent, api/views/data_analyst_agent.py).
 * Questions are answered read-only from the company's own database; only the question, its answer and its SQL are
 * kept, never the result's rows (they come back with the answer, and are run again when a question is reopened).
 */
export const getSetup = () => companyApi.get('/data-analyst/setup');
export const listSources = () => companyApi.get('/data-analyst/sources');
export const getSource = (id) => companyApi.get(`/data-analyst/sources/${id}`);
export const addConnection = (fields) => companyApi.post('/data-analyst/sources', fields);
export const uploadSqlite = (file, fields = {}) => {
  const form = new FormData();
  form.append('file', file);
  Object.entries(fields).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((v) => form.append(key, v));
    else if (value !== undefined && value !== null) form.append(key, value);
  });
  return companyApi.post('/data-analyst/sources', form);
};
export const updateSource = (id, fields) => companyApi.patch(`/data-analyst/sources/${id}`, fields);
export const removeSource = (id) => companyApi.delete(`/data-analyst/sources/${id}`);
export const testSource = (id) => companyApi.post(`/data-analyst/sources/${id}/test`, {});

export const ask = (source, question, conversation) =>
  companyApi.post('/data-analyst/ask', { source, question, ...(conversation ? { conversation } : {}) });
export const listQuestions = (params = {}) => companyApi.get('/data-analyst/questions', params);
export const runAgain = (id) => companyApi.post(`/data-analyst/questions/${id}/run`, {});

/** The result as a CSV, run again now; saved by the browser, nothing kept by us. */
export const downloadCsv = async (id) => {
  const blob = await companyApi.get(`/data-analyst/questions/${id}/csv`, { responseType: 'blob' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `question-${id}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const listLogins = () => companyApi.get('/company/logins');
