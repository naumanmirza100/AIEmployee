/**
 * HR for the signed-in employee (My Space). The server takes the person from the
 * sign-in only; nothing here names an employee.
 */
import api from './api';

const myHrService = {
  /** { available, employee, balances, leave_requests, leave_types } or { available: false, message } */
  get: () => api.get('/user/hr'),
  requestLeave: (payload) => api.post('/user/hr/leave', payload),
  cancelLeave: (id) => api.post(`/user/hr/leave/${id}/cancel`, {}),
  /** { answer, has_verified_info, sources: [{ title }] } */
  ask: (question) => api.post('/user/hr/ask', { question }),
};

export default myHrService;
