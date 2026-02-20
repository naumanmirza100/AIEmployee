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

export default {
  projectPilot,
  projectPilotFromFile,
  taskPrioritization,
  knowledgeQA,
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
};



