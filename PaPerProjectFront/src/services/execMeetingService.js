import { companyApi } from './companyAuthService';

const BASE = '/exec-meeting';

// Backend response shapes:
//   GET /meetings       → { status, meetings: [...], count }
//   GET /tasks          → { status, tasks: [...], count }
//   GET /notifications  → { status, notifications: [...] }

const execMeetingService = {
  // Stats — derive from list endpoints
  getStats: async () => {
    try {
      const [mRes, tRes, nRes] = await Promise.all([
        companyApi.get(`${BASE}/meetings`),
        companyApi.get(`${BASE}/tasks`),
        companyApi.get(`${BASE}/notifications`),
      ]);
      const meetings = mRes.meetings || [];
      const tasks    = tRes.tasks    || [];
      const notifs   = nRes.notifications || [];
      const now = new Date();
      return {
        upcoming_meetings:    meetings.filter(m => m.status === 'scheduled' && new Date(m.scheduled_at) > now).length,
        total_tasks:          tasks.length,
        overdue_tasks:        tasks.filter(t => t.due_date && new Date(t.due_date) < now && !['done','completed'].includes(t.status)).length,
        pending_action_items: tasks.filter(t => t.status !== 'done').length,
        unread_notifications: notifs.filter(n => !n.is_read).length,
      };
    } catch {
      return { upcoming_meetings: 0, total_tasks: 0, overdue_tasks: 0, pending_action_items: 0, unread_notifications: 0 };
    }
  },

  getDailyDigest: () => companyApi.post(`${BASE}/notifications/daily-digest`, {}),

  // Meetings — returns raw response; callers do res.meetings || []
  getMeetings: (params = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    const qs = q.toString();
    return companyApi.get(`${BASE}/meetings${qs ? `?${qs}` : ''}`);
  },
  getMeeting:    (id)          => companyApi.get(`${BASE}/meetings/${id}`),
  createMeeting: (payload)     => companyApi.post(`${BASE}/meetings`, payload),
  updateMeeting: (id, payload) => companyApi.patch(`${BASE}/meetings/${id}`, payload),
  deleteMeeting: (id)          => companyApi.delete(`${BASE}/meetings/${id}`),

  getMeetingNotes: (meetingId)          => companyApi.get(`${BASE}/meetings/${meetingId}/notes`),
  generateNotes:   (meetingId, payload) => companyApi.post(`${BASE}/meetings/${meetingId}/notes`, payload),
  convertActionItemToTask: (itemId, payload = {}) => companyApi.post(`${BASE}/action-items/${itemId}/convert-to-task`, payload),
  generateMeetingDescription: (title, points) => companyApi.post(`${BASE}/ai/generate-description`, { title, points }),
  checkMeetingConflicts: (payload) => companyApi.post(`${BASE}/meetings/check-conflicts`, payload),

  // Tasks — returns raw response; callers do res.tasks || []
  getTasks: (params = {}) => {
    const q = new URLSearchParams();
    if (params.status)   q.set('status', params.status);
    if (params.priority) q.set('priority', params.priority);
    const qs = q.toString();
    return companyApi.get(`${BASE}/tasks${qs ? `?${qs}` : ''}`);
  },
  createTask:     (payload)     => companyApi.post(`${BASE}/tasks`, payload),
  updateTask:     (id, payload) => companyApi.patch(`${BASE}/tasks/${id}`, payload),
  deleteTask:     (id)          => companyApi.delete(`${BASE}/tasks/${id}`),
  prioritizeTasks: ()           => companyApi.post(`${BASE}/tasks/ai/prioritize`, {}),
  generateTaskDescription: (title, points) => companyApi.post(`${BASE}/tasks/ai/generate-description`, { title, points }),

  // Calendar
  planWeek:       (opts = {}) => companyApi.post(`${BASE}/calendar/plan-week`, opts),
  getFreeSlots:   (payload) => companyApi.get(`${BASE}/calendar/free-slots`, { params: payload }),

  // Documents
  generateDocument: (payload) => {
    const { action, ...rest } = payload;
    return companyApi.post(`${BASE}/documents/draft`, { doc_type: action, ...rest });
  },
  listDocuments:   (params = {}) => {
    const q = new URLSearchParams();
    if (params.doc_type) q.set('doc_type', params.doc_type);
    const qs = q.toString();
    return companyApi.get(`${BASE}/documents${qs ? `?${qs}` : ''}`);
  },
  getDocument:    (id) => companyApi.get(`${BASE}/documents/${id}`),
  deleteDocument: (id) => companyApi.delete(`${BASE}/documents/${id}`),

  // Participants
  searchUsers:       (q) => companyApi.get(`${BASE}/users/search?q=${encodeURIComponent(q)}`),
  getParticipants:   (meetingId) => companyApi.get(`${BASE}/meetings/${meetingId}/participants`),
  addParticipant:    (meetingId, userId, userType) => companyApi.post(`${BASE}/meetings/${meetingId}/participants`, { user_id: userId, user_type: userType || 'company_user' }),
  removeParticipant: (meetingId, participantId, userId) => companyApi.delete(`${BASE}/meetings/${meetingId}/participants`, { data: { participant_id: participantId, user_id: userId } }),

  // Notifications — returns raw response; callers do res.notifications || []
  getNotifications: (params = {}) => {
    const q = new URLSearchParams();
    if (params.unread_only) q.set('unread', 'true');
    const qs = q.toString();
    return companyApi.get(`${BASE}/notifications${qs ? `?${qs}` : ''}`);
  },
  markNotificationRead: (id) => companyApi.patch(`${BASE}/notifications/${id}/read`, {}),
  markAllRead:          ()   => companyApi.patch(`${BASE}/notifications/mark-all-read`, {}),
  deleteNotification:   (id) => companyApi.delete(`${BASE}/notifications/${id}`),
  bulkDeleteNotifications: (ids) => companyApi.post(`${BASE}/notifications/bulk-delete`, { ids }),
};

export default execMeetingService;
