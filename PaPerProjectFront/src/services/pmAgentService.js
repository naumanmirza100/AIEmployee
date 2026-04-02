// Project Manager Agent Service

import { companyApi } from './companyAuthService';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Project Pilot Agent - Create projects, tasks, and manage operations
 * @param {string} question
 * @param {number|null} projectId
 * @param {Array<{role: string, content: string}>} chatHistory - Optional conversation history for this chat
 */
export const projectPilot = async (question, projectId = null, chatHistory = null) => {
  try {
    const body = {
      question: question.trim(),
      project_id: projectId || null,
    };
    if (Array.isArray(chatHistory) && chatHistory.length > 0) {
      body.chat_history = chatHistory.map((m) => ({ role: m.role, content: m.content || '' }));
    }
    const response = await companyApi.post('/project-manager/ai/project-pilot', body);
    return response;
  } catch (error) {
    console.error('Project Pilot error:', error);
    throw error;
  }
};

/**
 * Task Prioritization Agent
 * @param {string} action - 'prioritize' | 'order' | 'bottlenecks' | 'delegation'
 * @param {number|null} projectId - Optional project ID
 * @param {object} task - Optional task data for some actions
 */
export const taskPrioritization = async (action = 'prioritize', projectId = null, task = {}) => {
  try {
    const response = await companyApi.post('/project-manager/ai/task-prioritization', {
      action,
      project_id: projectId || null,
      task: task || {},
    });
    return response;
  } catch (error) {
    console.error('Task Prioritization error:', error);
    throw error;
  }
};

/**
 * Knowledge Q&A Agent - Answer questions about projects
 * @param {string} question
 * @param {number|null} projectId
 * @param {Array<{role: string, content: string}>} chatHistory - Optional conversation history for this chat
 */
export const knowledgeQA = async (question, projectId = null, chatHistory = null) => {
  try {
    const body = {
      question: question.trim(),
      project_id: projectId || null,
    };
    if (Array.isArray(chatHistory) && chatHistory.length > 0) {
      body.chat_history = chatHistory.map((m) => ({ role: m.role, content: m.content || '' }));
    }
    const response = await companyApi.post('/project-manager/ai/knowledge-qa', body);
    return response;
  } catch (error) {
    console.error('Knowledge Q&A error:', error);
    throw error;
  }
};

/** List all Knowledge QA chats */
export const listKnowledgeQAChats = async () => {
  const response = await companyApi.get('/project-manager/ai/knowledge-qa/chats');
  return response;
};

/** Create a new Knowledge QA chat */
export const createKnowledgeQAChat = async (data) => {
  const response = await companyApi.post('/project-manager/ai/knowledge-qa/chats/create', data);
  return response;
};

/** Update a Knowledge QA chat (add messages, optional title) */
export const updateKnowledgeQAChat = async (chatId, data) => {
  const response = await companyApi.patch(`/project-manager/ai/knowledge-qa/chats/${chatId}/update`, data);
  return response;
};

/** Delete a Knowledge QA chat */
export const deleteKnowledgeQAChat = async (chatId) => {
  const response = await companyApi.delete(`/project-manager/ai/knowledge-qa/chats/${chatId}/delete`);
  return response;
};

/** List all Project Pilot chats */
export const listProjectPilotChats = async () => {
  const response = await companyApi.get('/project-manager/ai/project-pilot/chats');
  return response;
};

/** Create a new Project Pilot chat */
export const createProjectPilotChat = async (data) => {
  const response = await companyApi.post('/project-manager/ai/project-pilot/chats/create', data);
  return response;
};

/** Update a Project Pilot chat (add messages, optional title) */
export const updateProjectPilotChat = async (chatId, data) => {
  const response = await companyApi.patch(`/project-manager/ai/project-pilot/chats/${chatId}/update`, data);
  return response;
};

/** Delete a Project Pilot chat */
export const deleteProjectPilotChat = async (chatId) => {
  const response = await companyApi.delete(`/project-manager/ai/project-pilot/chats/${chatId}/delete`);
  return response;
};

/**
 * Generate a graph/chart from a natural language prompt (Project Manager)
 * @param {string} prompt
 * @param {number|null} projectId
 */
export const generateGraph = async (prompt, projectId = null) => {
  try {
    const response = await companyApi.post('/project-manager/ai/generate-graph', {
      prompt: (prompt || '').trim(),
      project_id: projectId || null,
    });
    return response;
  } catch (error) {
    console.error('PM generate graph error:', error);
    throw error;
  }
};

/**
 * Timeline/Gantt Agent
 * @param {string} action - 'create_timeline' | 'generate_gantt_chart' | 'check_deadlines' | 'suggest_adjustments' | 'calculate_duration' | 'manage_phases'
 * @param {number} projectId - Required project ID
 * @param {object} options - Additional options based on action
 */
export const timelineGantt = async (action = 'create_timeline', projectId, options = {}) => {
  try {
    if (!projectId) {
      throw new Error('project_id is required for timeline/gantt operations');
    }

    const payload = {
      action,
      project_id: projectId,
      ...options,
    };

    const response = await companyApi.post('/project-manager/ai/timeline-gantt', payload);
    return response;
  } catch (error) {
    console.error('Timeline/Gantt error:', error);
    throw error;
  }
};

/**
 * Generate Subtasks for a project
 * @param {number} projectId - Required project ID
 */
export const generateSubtasks = async (projectId) => {
  try {
    if (!projectId) {
      throw new Error('project_id is required for subtask generation');
    }

    const response = await companyApi.post('/project-manager/ai/generate-subtasks', {
      project_id: projectId,
    });
    return response;
  } catch (error) {
    console.error('Generate Subtasks error:', error);
    throw error;
  }
};

/**
 * Project Pilot from File - Upload a file and process its content
 * @param {File} file - File to upload (txt, pdf, or docx)
 * @param {number|null} projectId - Optional project ID
 * @param {Array<{role: string, content: string}>} chatHistory - Optional conversation history for this chat
 */
export const projectPilotFromFile = async (file, projectId = null, chatHistory = null) => {
  try {
    const token = localStorage.getItem('company_auth_token');

    const formData = new FormData();
    formData.append('file', file);
    if (projectId) {
      formData.append('project_id', projectId);
    }
    if (Array.isArray(chatHistory) && chatHistory.length > 0) {
      formData.append('chat_history', JSON.stringify(chatHistory.map((m) => ({ role: m.role, content: m.content || '' }))));
    }

    const response = await fetch(`${API_BASE_URL}/project-manager/ai/project-pilot/upload-file`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${token}`,
      },
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || `HTTP error! status: ${response.status}`);
    }
    return data;
  } catch (error) {
    console.error('Project Pilot from File error:', error);
    throw error;
  }
};

/**
 * Daily Standup - Generate daily or weekly standup reports
 */
export const dailyStandup = async (projectId = null, action = 'daily') => {
  try {
    const response = await companyApi.post('/project-manager/ai/daily-standup', {
      project_id: projectId || null,
      action,
    });
    return response;
  } catch (error) {
    console.error('Daily Standup error:', error);
    throw error;
  }
};

/**
 * Project Health Score
 */
export const projectHealth = async (projectId, action = 'health') => {
  try {
    const response = await companyApi.post('/project-manager/ai/project-health', {
      project_id: projectId,
      action,
    });
    return response;
  } catch (error) {
    console.error('Project Health error:', error);
    throw error;
  }
};

/**
 * Project Status Report
 */
export const statusReport = async (projectId) => {
  try {
    const response = await companyApi.post('/project-manager/ai/status-report', {
      project_id: projectId,
    });
    return response;
  } catch (error) {
    console.error('Status Report error:', error);
    throw error;
  }
};

/**
 * Meeting Notes - Summarize meeting text and extract action items
 */
export const meetingNotes = async (meetingText, projectId = null, action = 'summarize') => {
  try {
    const response = await companyApi.post('/project-manager/ai/meeting-notes', {
      meeting_text: meetingText,
      project_id: projectId || null,
      action,
    });
    return response;
  } catch (error) {
    console.error('Meeting Notes error:', error);
    throw error;
  }
};

/**
 * Workflow Suggestions
 */
export const workflowSuggest = async (projectId, action = 'suggest', phase = 'development') => {
  try {
    const response = await companyApi.post('/project-manager/ai/workflow-suggest', {
      project_id: projectId,
      action,
      phase,
    });
    return response;
  } catch (error) {
    console.error('Workflow Suggest error:', error);
    throw error;
  }
};

/**
 * Calendar Schedule
 */
export const calendarSchedule = async (projectId, action = 'schedule') => {
  try {
    const response = await companyApi.post('/project-manager/ai/calendar-schedule', {
      project_id: projectId,
      action,
    });
    return response;
  } catch (error) {
    console.error('Calendar Schedule error:', error);
    throw error;
  }
};

/**
 * Smart Notifications - Scan for issues
 */
export const scanNotifications = async (projectId = null) => {
  try {
    const response = await companyApi.post('/project-manager/ai/notifications/scan', {
      project_id: projectId || null,
    });
    return response;
  } catch (error) {
    console.error('Scan Notifications error:', error);
    throw error;
  }
};

/**
 * List Notifications
 */
export const listNotifications = async (unreadOnly = false, limit = 50) => {
  try {
    const response = await companyApi.get(`/project-manager/ai/notifications?unread_only=${unreadOnly}&limit=${limit}`);
    return response;
  } catch (error) {
    console.error('List Notifications error:', error);
    throw error;
  }
};

/**
 * Mark Notifications Read
 */
export const markNotificationsRead = async (notificationIds = [], markAll = false) => {
  try {
    const response = await companyApi.post('/project-manager/ai/notifications/read', {
      notification_ids: notificationIds,
      mark_all: markAll,
    });
    return response;
  } catch (error) {
    console.error('Mark Notifications Read error:', error);
    throw error;
  }
};

/**
 * Team Performance
 */
export const teamPerformance = async (projectId) => {
  try {
    const response = await companyApi.post('/project-manager/ai/team-performance', {
      project_id: projectId,
    });
    return response;
  } catch (error) {
    console.error('Team Performance error:', error);
    throw error;
  }
};

/**
 * Time Estimation
 */
export const timeEstimation = async (projectId) => {
  try {
    const response = await companyApi.post('/project-manager/ai/time-estimation', {
      project_id: projectId,
    });
    return response;
  } catch (error) {
    console.error('Time Estimation error:', error);
    throw error;
  }
};

/**
 * Meeting Scheduler - Send a chat message to schedule a meeting
 */
export const meetingSchedule = async (message) => {
  try {
    const response = await companyApi.post('/project-manager/ai/meetings/schedule', { message });
    return response;
  } catch (error) {
    console.error('Meeting schedule error:', error);
    throw error;
  }
};

/**
 * Meeting Respond - Accept, reject, counter-propose, or withdraw a meeting
 */
export const meetingRespond = async (meetingId, action, reason = '', counterTime = null) => {
  try {
    const response = await companyApi.post('/project-manager/ai/meetings/respond', {
      meeting_id: meetingId,
      action,
      reason,
      counter_time: counterTime,
    });
    return response;
  } catch (error) {
    console.error('Meeting respond error:', error);
    throw error;
  }
};

/**
 * Meeting List - Get all meetings for current user
 */
export const meetingList = async (statusFilter = '', roleFilter = '') => {
  try {
    let url = '/project-manager/ai/meetings';
    const params = [];
    if (statusFilter) params.push(`status=${statusFilter}`);
    if (roleFilter) params.push(`role=${roleFilter}`);
    if (params.length) url += '?' + params.join('&');
    const response = await companyApi.get(url);
    return response;
  } catch (error) {
    console.error('Meeting list error:', error);
    throw error;
  }
};

export const listMeetingSchedulerChats = async () => {
  try {
    const response = await companyApi.get('/project-manager/ai/meeting-scheduler/chats');
    return response?.data || { status: 'success', data: [] };
  } catch (error) { console.error('List meeting chats error:', error); return { status: 'success', data: [] }; }
};

export const createMeetingSchedulerChat = async (data = {}) => {
  try {
    const response = await companyApi.post('/project-manager/ai/meeting-scheduler/chats/create', data);
    return response?.data || {};
  } catch (error) { console.error('Create meeting chat error:', error); throw error; }
};

export const updateMeetingSchedulerChat = async (chatId, data = {}) => {
  try {
    const response = await companyApi.patch(`/project-manager/ai/meeting-scheduler/chats/${chatId}/update`, data);
    return response?.data || {};
  } catch (error) { console.error('Update meeting chat error:', error); throw error; }
};

export const deleteMeetingSchedulerChat = async (chatId) => {
  try {
    const response = await companyApi.delete(`/project-manager/ai/meeting-scheduler/chats/${chatId}/delete`);
    return response?.data || {};
  } catch (error) { console.error('Delete meeting chat error:', error); throw error; }
};

export default {
  projectPilot,
  projectPilotFromFile,
  taskPrioritization,
  knowledgeQA,
  generateGraph,
  listKnowledgeQAChats,
  createKnowledgeQAChat,
  updateKnowledgeQAChat,
  deleteKnowledgeQAChat,
  listProjectPilotChats,
  createProjectPilotChat,
  updateProjectPilotChat,
  deleteProjectPilotChat,
  timelineGantt,
  generateSubtasks,
  dailyStandup,
  projectHealth,
  statusReport,
  meetingNotes,
  workflowSuggest,
  calendarSchedule,
  scanNotifications,
  listNotifications,
  markNotificationsRead,
  teamPerformance,
  timeEstimation,
  meetingSchedule,
  meetingRespond,
  meetingList,
  listMeetingSchedulerChats,
  createMeetingSchedulerChat,
  updateMeetingSchedulerChat,
  deleteMeetingSchedulerChat,
};



