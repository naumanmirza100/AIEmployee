// Project Manager Agent Service

import { companyApi } from './companyAuthService';

/**
 * Project Pilot Agent - Create projects, tasks, and manage operations
 */
export const projectPilot = async (question, projectId = null) => {
  try {
    const response = await companyApi.post('/project-manager/ai/project-pilot', {
      question: question.trim(),
      project_id: projectId || null,
    });
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
 */
export const knowledgeQA = async (question, projectId = null) => {
  try {
    const response = await companyApi.post('/project-manager/ai/knowledge-qa', {
      question: question.trim(),
      project_id: projectId || null,
    });
    return response;
  } catch (error) {
    console.error('Knowledge Q&A error:', error);
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
 */
export const projectPilotFromFile = async (file, projectId = null) => {
  try {
    const token = localStorage.getItem('company_auth_token');
    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

    const formData = new FormData();
    formData.append('file', file);
    if (projectId) {
      formData.append('project_id', projectId);
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
  timelineGantt,
  generateSubtasks,
};



