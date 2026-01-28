import { companyApi } from './companyAuthService';

const companyProjectsTasksService = {
  /**
   * Update a project
   * @param {number} projectId - Project ID
   * @param {object} data - Project data to update (name, description, status, priority, etc.)
   * @returns {Promise} API response
   */
  async updateProject(projectId, data) {
    try {
      const response = await companyApi.put(`/company/projects/${projectId}/update`, data);
      return response;
    } catch (error) {
      console.error('Error updating project:', error);
      throw error;
    }
  },

  /**
   * Update a task
   * @param {number} taskId - Task ID
   * @param {object} data - Task data to update (title, description, priority, assignee_id, etc.)
   * @returns {Promise} API response
   */
  async updateTask(taskId, data) {
    try {
      const response = await companyApi.put(`/company/tasks/${taskId}/update`, data);
      return response;
    } catch (error) {
      console.error('Error updating task:', error);
      throw error;
    }
  },

  /**
   * Get list of users for task assignment
   * @returns {Promise} API response with list of users
   */
  async getUsersForAssignment() {
    try {
      const response = await companyApi.get('/company/users/for-assignment');
      return response;
    } catch (error) {
      console.error('Error fetching users for assignment:', error);
      throw error;
    }
  },
};

export default companyProjectsTasksService;

