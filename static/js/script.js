document.addEventListener("DOMContentLoaded", function () {
  // Elements
  const messagesContainer = document.getElementById("messages");
  const userInput = document.getElementById("userInput");
  const sendButton = document.getElementById("sendButton");
  const ticketList = document.getElementById("ticketList");
  const ticketDetails = document.getElementById("ticketDetails");

  // Analytics elements
  const totalQueriesEl = document.getElementById("totalQueries");
  const aiResolvedEl = document.getElementById("aiResolved");
  const humanResolvedEl = document.getElementById("humanResolved");
  const learningEventsEl = document.getElementById("learningEvents");
  const aiResolvedBar = document.getElementById("aiResolvedBar");
  const humanResolvedBar = document.getElementById("humanResolvedBar");

  // State
  let selectedTicketId = null;
  let selectedTicket = null;
  let sessionId = localStorage.getItem("chatSessionId");

  // Create session if none exists
  async function ensureSession() {
    if (!sessionId) {
      try {
        const response = await fetch("/api/session");
        const data = await response.json();
        sessionId = data.sessionId;
        localStorage.setItem("chatSessionId", sessionId);
      } catch (error) {
        console.error("Error creating session:", error);
        // Fallback session ID
        sessionId = "user-" + Date.now();
        localStorage.setItem("chatSessionId", sessionId);
      }
    }
  }

  // Initialize session
  ensureSession();

  // Function to add message to chat
  function addMessage(text, type) {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add(type + "-message");
    messageDiv.textContent = text;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Function to show typing indicator
  function showTypingIndicator() {
    const indicatorDiv = document.createElement("div");
    indicatorDiv.classList.add("typing-indicator");
    indicatorDiv.id = "typingIndicator";
    indicatorDiv.innerHTML = "<span></span><span></span><span></span>";
    messagesContainer.appendChild(indicatorDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Function to remove typing indicator
  function removeTypingIndicator() {
    const indicator = document.getElementById("typingIndicator");
    if (indicator) {
      indicator.remove();
    }
  }

  // Send message function
  async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) return;

    // Add user message to chat
    addMessage(message, "user");
    userInput.value = "";

    // Show typing indicator
    showTypingIndicator();

    try {
      // Send to backend
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: message,
          sessionId: sessionId,
        }),
      });

      const data = await response.json();

      // Remove typing indicator
      removeTypingIndicator();

      // Handle human handoff
      if (data.needsHuman) {
        addMessage(data.response, "bot");

        // Add system message about ticket creation
        setTimeout(() => {
          addMessage(
            "Your question has been sent to our support team. They'll respond shortly.",
            "system"
          );
        }, 1000);
      } else {
        // Normal bot response
        addMessage(data.response, "bot");
      }

      // Update analytics
      updateAnalytics();
    } catch (error) {
      console.error("Error:", error);
      removeTypingIndicator();
      addMessage("Sorry, something went wrong. Please try again.", "system");
    }
  }

  // Send button event
  sendButton.addEventListener("click", sendMessage);

  // Send on Enter key
  userInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      sendMessage();
    }
  });

  // Agent dashboard - fetch tickets
  async function fetchTickets() {
    try {
      const response = await fetch("/api/tickets");
      const data = await response.json();

      if (data.tickets.length === 0) {
        ticketList.innerHTML =
          '<li class="list-group-item text-center text-muted">No tickets available</li>';
        return;
      }

      ticketList.innerHTML = "";
      data.tickets.forEach((ticket) => {
        const li = document.createElement("li");
        li.classList.add("list-group-item");
        li.textContent = `Session ${ticket.sessionId.substring(0, 8)}...`;
        li.addEventListener("click", () => selectTicket(ticket));
        if (selectedTicketId === ticket.sessionId) {
          li.classList.add("selected-ticket");
        }
        ticketList.appendChild(li);
      });
    } catch (error) {
      console.error("Error fetching tickets:", error);
    }
  }

  // Select ticket function
  function selectTicket(ticket) {
    selectedTicketId = ticket.sessionId;
    selectedTicket = ticket;

    // Update UI to show selected ticket
    document.querySelectorAll("#ticketList li").forEach((li) => {
      li.classList.remove("selected-ticket");
      if (li.textContent === `Session ${ticket.sessionId.substring(0, 8)}...`) {
        li.classList.add("selected-ticket");
      }
    });

    // Display conversation
    let html = `
            <div class="conversation-container">
        `;

    ticket.conversation.forEach((msg) => {
      if (msg.role === "user") {
        html += `<div class="user-message mb-2"><strong>Customer:</strong> ${msg.content}</div>`;
      } else {
        html += `<div class="bot-message mb-2"><strong>AI:</strong> ${msg.content}</div>`;
      }
    });

    html += `
            </div>
            <div class="form-group mb-3">
                <label for="agentResponse"><strong>Your Response:</strong></label>
                <textarea class="form-control response-textarea" id="agentResponse"></textarea>
            </div>
            <button class="btn btn-success" id="submitResponse">Submit Response</button>
        `;

    ticketDetails.innerHTML = html;

    // Add event listener to submit button
    document
      .getElementById("submitResponse")
      .addEventListener("click", submitAgentResponse);
  }

  // Submit agent response
  async function submitAgentResponse() {
    const responseText = document.getElementById("agentResponse").value.trim();
    if (!responseText || !selectedTicket) return;

    // Get the last user question
    const userMessages = selectedTicket.conversation.filter(
      (msg) => msg.role === "user"
    );
    const lastQuestion = userMessages[userMessages.length - 1].content;

    try {
      const response = await fetch("/api/human-response", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sessionId: selectedTicketId,
          question: lastQuestion,
          answer: responseText,
        }),
      });

      const data = await response.json();

      if (data.success) {
        // Reset UI
        ticketDetails.innerHTML = `
                    <div class="alert alert-success">
                        <h4 class="alert-heading">Response Submitted!</h4>
                        <p>Your response has been sent to the customer and added to our knowledge base.</p>
                        ${
                          data.learned
                            ? "<p><strong>New knowledge acquired!</strong> This answer will be used for similar questions in the future.</p>"
                            : ""
                        }
                    </div>
                `;
        selectedTicketId = null;
        selectedTicket = null;

        // Refresh tickets
        fetchTickets();

        // Update analytics
        updateAnalytics();
      }
    } catch (error) {
      console.error("Error submitting response:", error);
    }
  }

  // Update analytics
  async function updateAnalytics() {
    try {
      const response = await fetch("/api/analytics");
      const data = await response.json();

      // Update counter displays
      totalQueriesEl.textContent = data.total_queries;
      aiResolvedEl.textContent = data.ai_resolved;
      humanResolvedEl.textContent = data.human_resolved;
      learningEventsEl.textContent = data.learning_events;

      // Update progress bars
      const total = data.ai_resolved + data.human_resolved;
      if (total > 0) {
        const aiPercent = (data.ai_resolved / total) * 100;
        const humanPercent = (data.human_resolved / total) * 100;

        aiResolvedBar.style.width = `${aiPercent}%`;
        humanResolvedBar.style.width = `${humanPercent}%`;

        aiResolvedBar.textContent = `${Math.round(aiPercent)}%`;
        humanResolvedBar.textContent = `${Math.round(humanPercent)}%`;
      }
    } catch (error) {
      console.error("Error fetching analytics:", error);
    }
  }

  // Tab change events
  document.getElementById("agent-tab").addEventListener("click", fetchTickets);
  document
    .getElementById("analytics-tab")
    .addEventListener("click", updateAnalytics);

  // Periodically refresh tickets and analytics
  setInterval(fetchTickets, 10000);
  setInterval(updateAnalytics, 30000);

  // Initial analytics fetch
  updateAnalytics();
});
