// Frontline Agent Dashboard JavaScript

// Get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

// Knowledge Q&A Agent
document.getElementById('ask-question-btn')?.addEventListener('click', async () => {
    const question = document.getElementById('knowledge-question').value.trim();
    if (!question) {
        alert('Please enter a question');
        return;
    }

    const answerBox = document.getElementById('knowledge-answer');
    const answerContent = answerBox.querySelector('.answer-content');
    answerBox.style.display = 'block';
    answerContent.textContent = 'Loading...';

    try {
        const response = await fetch('/frontline/api/knowledge-qa/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ question })
        });

        const data = await response.json();
        if (data.success) {
            answerContent.textContent = data.answer;
        } else {
            answerContent.textContent = `Error: ${data.error || 'Failed to get answer'}`;
        }
    } catch (error) {
        answerContent.textContent = `Error: ${error.message}`;
    }
});

// Ticket Management
document.getElementById('create-ticket-btn')?.addEventListener('click', () => {
    document.getElementById('ticket-form').style.display = 'block';
});

document.getElementById('cancel-ticket-btn')?.addEventListener('click', () => {
    document.getElementById('ticket-form').style.display = 'none';
    document.getElementById('ticket-title').value = '';
    document.getElementById('ticket-description').value = '';
});

document.getElementById('submit-ticket-btn')?.addEventListener('click', async () => {
    const title = document.getElementById('ticket-title').value.trim();
    const description = document.getElementById('ticket-description').value.trim();
    const priority = document.getElementById('ticket-priority').value;
    const category = document.getElementById('ticket-category').value;

    if (!title || !description) {
        alert('Please fill in all required fields');
        return;
    }

    try {
        const response = await fetch('/frontline/api/tickets/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ title, description, priority, category })
        });

        const data = await response.json();
        if (data.success) {
            alert(`Ticket #${data.ticket_id} created successfully!`);
            document.getElementById('ticket-form').style.display = 'none';
            document.getElementById('ticket-title').value = '';
            document.getElementById('ticket-description').value = '';
            loadTickets();
        } else {
            alert(`Error: ${data.error || 'Failed to create ticket'}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
});

// Load Tickets
async function loadTickets() {
    const ticketsList = document.getElementById('tickets-list');
    if (!ticketsList) return;

    try {
        const response = await fetch('/frontline/api/tickets/');
        const data = await response.json();
        
        if (data.tickets) {
            ticketsList.innerHTML = data.tickets.map(ticket => `
                <div class="ticket-item">
                    <div class="ticket-header">
                        <span class="ticket-id">#${ticket.id}</span>
                        <span class="ticket-status status-${ticket.status}">${ticket.status}</span>
                    </div>
                    <h4>${ticket.title}</h4>
                    <p>${ticket.description}</p>
                    <p class="ticket-meta">Created: ${new Date(ticket.created_at).toLocaleString()}</p>
                    ${ticket.auto_resolved ? '<span class="badge">Auto-Resolved</span>' : ''}
                </div>
            `).join('');
        }
    } catch (error) {
        ticketsList.innerHTML = `<div class="error">Error loading tickets: ${error.message}</div>`;
    }
}

// Load Notifications
async function loadNotifications() {
    const notificationsList = document.getElementById('notifications-list');
    if (!notificationsList) return;

    try {
        const response = await fetch('/frontline/api/notifications/?unread_only=true');
        const data = await response.json();
        
        if (data.notifications) {
            notificationsList.innerHTML = data.notifications.map(notif => `
                <div class="notification-item ${notif.is_read ? '' : 'unread'}" data-id="${notif.id}">
                    <h4>${notif.title}</h4>
                    <p>${notif.message}</p>
                    <p class="notification-meta">${new Date(notif.created_at).toLocaleString()}</p>
                </div>
            `).join('') || '<p class="empty-state">No notifications</p>';

            // Add click handlers
            document.querySelectorAll('.notification-item').forEach(item => {
                item.addEventListener('click', async () => {
                    const id = item.dataset.id;
                    await markNotificationRead(id);
                    item.classList.remove('unread');
                });
            });
        }
    } catch (error) {
        notificationsList.innerHTML = `<div class="error">Error loading notifications: ${error.message}</div>`;
    }
}

async function markNotificationRead(id) {
    try {
        await fetch(`/frontline/api/notifications/${id}/read/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            }
        });
    } catch (error) {
        console.error('Error marking notification as read:', error);
    }
}

// Workflow Execution
document.getElementById('execute-workflow-btn')?.addEventListener('click', async () => {
    const workflowName = document.getElementById('workflow-name').value.trim();
    const workflowDescription = document.getElementById('workflow-description').value.trim();

    if (!workflowName) {
        alert('Please enter a workflow name');
        return;
    }

    const resultBox = document.getElementById('workflow-result');
    resultBox.style.display = 'block';
    resultBox.innerHTML = '<div class="loading">Executing workflow...</div>';

    try {
        const response = await fetch('/frontline/api/workflows/execute/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                workflow_name: workflowName,
                workflow_description: workflowDescription,
                context_data: {}
            })
        });

        const data = await response.json();
        if (data.success) {
            resultBox.innerHTML = `<div class="success">Workflow executed successfully! Execution ID: ${data.execution_id}</div>`;
        } else {
            resultBox.innerHTML = `<div class="error">Error: ${data.error || 'Failed to execute workflow'}</div>`;
        }
    } catch (error) {
        resultBox.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
});

// Meeting Scheduling
document.getElementById('schedule-meeting-btn')?.addEventListener('click', async () => {
    const title = document.getElementById('meeting-title').value.trim();
    const description = document.getElementById('meeting-description').value.trim();
    const datetime = document.getElementById('meeting-datetime').value;
    const duration = document.getElementById('meeting-duration').value;
    const link = document.getElementById('meeting-link').value.trim();

    if (!title || !datetime) {
        alert('Please fill in title and datetime');
        return;
    }

    const resultBox = document.getElementById('meeting-result');
    resultBox.style.display = 'block';
    resultBox.innerHTML = '<div class="loading">Scheduling meeting...</div>';

    try {
        const response = await fetch('/frontline/api/meetings/schedule/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                title,
                description,
                scheduled_at: datetime,
                duration_minutes: parseInt(duration) || 60,
                meeting_link: link,
                participant_ids: []
            })
        });

        const data = await response.json();
        if (data.success) {
            resultBox.innerHTML = `<div class="success">Meeting scheduled successfully! Meeting ID: ${data.meeting_id}</div>`;
        } else {
            resultBox.innerHTML = `<div class="error">Error: ${data.error || 'Failed to schedule meeting'}</div>`;
        }
    } catch (error) {
        resultBox.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
});

// Document Upload
document.getElementById('upload-document-btn')?.addEventListener('click', async () => {
    const fileInput = document.getElementById('document-file');
    const title = document.getElementById('document-title').value.trim();

    if (!fileInput.files.length) {
        alert('Please select a file');
        return;
    }

    if (!title) {
        alert('Please enter a document title');
        return;
    }

    const resultBox = document.getElementById('document-result');
    resultBox.style.display = 'block';
    resultBox.innerHTML = '<div class="loading">Uploading document...</div>';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('title', title);
    formData.append('document_type', 'other');

    try {
        const response = await fetch('/frontline/api/documents/upload/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            },
            body: formData
        });

        const data = await response.json();
        if (data.success) {
            resultBox.innerHTML = `<div class="success">Document uploaded successfully! Document ID: ${data.document_id}</div>`;
            fileInput.value = '';
            document.getElementById('document-title').value = '';
        } else {
            resultBox.innerHTML = `<div class="error">Error: ${data.error || 'Failed to upload document'}</div>`;
        }
    } catch (error) {
        resultBox.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
});

// Analytics
document.getElementById('load-analytics-btn')?.addEventListener('click', async () => {
    const analyticsContent = document.getElementById('analytics-content');
    analyticsContent.style.display = 'block';
    analyticsContent.innerHTML = '<div class="loading">Loading analytics...</div>';

    try {
        const response = await fetch('/frontline/api/analytics/');
        const data = await response.json();

        if (data.error) {
            analyticsContent.innerHTML = `<div class="error">Error: ${data.error}</div>`;
        } else {
            const resolutionRate = data.resolution_rate ? data.resolution_rate.toFixed(1) : '0';
            document.getElementById('resolution-rate').textContent = `${resolutionRate}%`;

            analyticsContent.innerHTML = `
                <div class="analytics-item">
                    <h4>Total Tickets</h4>
                    <div class="analytics-value">${data.total_tickets || 0}</div>
                </div>
                <div class="analytics-item">
                    <h4>Open Tickets</h4>
                    <div class="analytics-value">${data.open_tickets || 0}</div>
                </div>
                <div class="analytics-item">
                    <h4>Resolved Tickets</h4>
                    <div class="analytics-value">${data.resolved_tickets || 0}</div>
                </div>
                <div class="analytics-item">
                    <h4>Auto-Resolved</h4>
                    <div class="analytics-value">${data.auto_resolved_count || 0}</div>
                </div>
                <div class="analytics-item">
                    <h4>Resolution Rate</h4>
                    <div class="analytics-value">${resolutionRate}%</div>
                </div>
                <div class="analytics-item">
                    <h4>Auto-Resolution Rate</h4>
                    <div class="analytics-value">${data.auto_resolution_rate ? data.auto_resolution_rate.toFixed(1) : '0'}%</div>
                </div>
            `;
        }
    } catch (error) {
        analyticsContent.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
});

// Refresh Notifications
document.getElementById('refresh-notifications-btn')?.addEventListener('click', loadNotifications);

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadTickets();
    loadNotifications();
    
    // Load analytics on page load
    document.getElementById('load-analytics-btn')?.click();
});

