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

  /**
   * Bulk update tasks (status / priority / assignee / due_date).
   * @param {object} payload - { ids: number[], status?, priority?, assignee_id?, due_date? }
   * @returns {Promise} API response with { updated, skipped, not_found, summary }
   */
  async bulkUpdateTasks(payload) {
    try {
      const response = await api.post('/user/project-manager/tasks/bulk-update', payload);
      return response;
    } catch (error) {
      console.error('Error bulk-updating tasks:', error);
      throw error;
    }
  },

  /**
   * Replace the dependency set for a task (T-F1).
   * @param {number} taskId
   * @param {number[]} dependsOnIds - prerequisite task IDs (pass [] to clear)
   * @returns {Promise} API response
   */
  async setTaskDependencies(taskId, dependsOnIds) {
    try {
      const response = await api.put(
        `/user/project-manager/tasks/${taskId}/dependencies`,
        { depends_on_ids: dependsOnIds }
      );
      return response;
    } catch (error) {
      console.error('Error setting task dependencies:', error);
      throw error;
    }
  },

  /**
   * Set or update a task's recurrence (T-F2).
   * @param {number} taskId
   * @param {object} recurrence - { frequency, interval?, weekdays?, starts_on, ends_on?, max_occurrences?, is_active? }
   */
  async setTaskRecurrence(taskId, recurrence) {
    try {
      const response = await api.put(
        `/user/project-manager/tasks/${taskId}/recurrence`,
        recurrence,
      );
      return response;
    } catch (error) {
      console.error('Error setting task recurrence:', error);
      throw error;
    }
  },

  /**
   * Remove a task's recurrence (T-F2).
   * @param {number} taskId
   */
  async deleteTaskRecurrence(taskId) {
    try {
      const response = await api.delete(
        `/user/project-manager/tasks/${taskId}/recurrence`,
      );
      return response;
    } catch (error) {
      console.error('Error deleting task recurrence:', error);
      throw error;
    }
  },
};

export default userProjectManagerService;

