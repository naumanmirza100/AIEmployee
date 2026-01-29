import api from './api';

const userProjectManagerService = {
  /**
   * Get all tasks from projects where the project manager has at least one task
   * @returns {Promise} API response
   */
  async getProjectsTasks() {
    try {
      const response = await api.get('/user/project-manager/projects-tasks');
      return response;
    } catch (error) {
      console.error('Error fetching projects tasks:', error);
      throw error;
    }
  },

  /**
   * Get all projects where the project manager has at least one task
   * @returns {Promise} API response
   */
  async getProjects() {
    try {
      const response = await api.get('/user/project-manager/projects');
      return response;
    } catch (error) {
      console.error('Error fetching projects:', error);
      throw error;
    }
  },

  /**
   * Create a new project
   * @param {object} data - Project data (name, description, status, priority, etc.)
   * @returns {Promise} API response
   */
  async createProject(data) {
    try {
      const response = await api.post('/user/project-manager/projects/create', data);
      return response;
    } catch (error) {
      console.error('Error creating project:', error);
      throw error;
    }
  },

  /**
   * Create a new task in a project
   * @param {object} data - Task data (project_id, title, description, assignee_id, etc.)
   * @returns {Promise} API response
   */
  async createTask(data) {
    try {
      const response = await api.post('/user/project-manager/tasks/create', data);
      return response;
    } catch (error) {
      console.error('Error creating task:', error);
      throw error;
    }
  },

  /**
   * Get list of company users for task assignment
   * @returns {Promise} API response
   */
  async getCompanyUsers() {
    try {
      const response = await api.get('/user/project-manager/company-users');
      return response;
    } catch (error) {
      console.error('Error fetching company users:', error);
      throw error;
    }
  },

  /**
   * Update a project
   * @param {number} projectId - Project ID
   * @param {object} data - Project data to update
   * @returns {Promise} API response
   */
  async updateProject(projectId, data) {
    try {
      const response = await api.put(`/user/project-manager/projects/${projectId}/update`, data);
      return response;
    } catch (error) {
      console.error('Error updating project:', error);
      throw error;
    }
  },

  /**
   * Update a task
   * @param {number} taskId - Task ID
   * @param {object} data - Task data to update
   * @returns {Promise} API response
   */
  async updateTask(taskId, data) {
    try {
      const response = await api.put(`/user/project-manager/tasks/${taskId}/update`, data);
      return response;
    } catch (error) {
      console.error('Error updating task:', error);
      throw error;
    }
  },
};

export default userProjectManagerService;

