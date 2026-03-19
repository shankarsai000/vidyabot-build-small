/**
 * API Helper Functions
 * Handles all communication with backend
 */

const API = {
  BASE_URL: '',  // Relative URL - same server
  
  // Helper for JSON API calls
  async call(endpoint, method = 'GET', body = null) {
    const options = {
      method,
      headers: {
        'Content-Type': 'application/json',
      }
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    try {
      const response = await fetch(`${this.BASE_URL}${endpoint}`, options);
      
      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API call failed:', error);
      throw error;
    }
  },

  // Health check
  async health() {
    return this.call('/api/health');
  },

  // Get list of textbooks
  async getTextbooks() {
    return this.call('/api/textbooks');
  },

  // Upload PDF file
  async uploadPDF(file, board, subject, grade, title, onProgress = null) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('board', board);
    formData.append('subject', subject);
    formData.append('grade', grade);
    formData.append('title', title);

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      // Progress event
      if (onProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const percentComplete = (event.loaded / event.total) * 100;
            onProgress(percentComplete);
          }
        });
      }

      // Success
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve(response);
          } catch (e) {
            reject(new Error('Failed to parse response'));
          }
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      });

      // Error
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload cancelled'));
      });

      xhr.open('POST', `${this.BASE_URL}/api/ingest`);
      xhr.send(formData);
    });
  },

  // Ask question
  async query(question, textbookId, language = 'english', mode = 'answer') {
    return this.call('/api/query', 'POST', {
      question,
      textbook_id: parseInt(textbookId),
      language,
      mode
    });
  },

  // Get statistics
  async getStats() {
    return this.call('/api/stats');
  },

  // Get cache statistics
  async getCacheStats() {
    return this.call('/api/stats/cache');
  },

  // Get recent queries
  async getRecentQueries(limit = 10) {
    return this.call(`/api/stats/queries/recent?limit=${limit}`);
  },

  // Get daily statistics
  async getDailyStats() {
    return this.call('/api/stats/by-date');
  }
};
