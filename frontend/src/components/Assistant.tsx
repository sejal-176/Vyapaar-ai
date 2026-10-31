import React, { useState, useEffect, useRef } from "react";
import type { AgentToolCall, Merchant } from "../api/types";
import { sendAgentMessage } from "../api/client";

interface AssistantProps {
  merchantId: number;
  merchants: Merchant[];
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
  tools_used?: AgentToolCall[];
  mode?: string;
  isError?: boolean;
}

const PROMPT_CHIPS = [
  "How much did I collect today?",
  "Why were collections lower than yesterday?",
  "When do I get the most payments?",
  "Create a daily report",
];

export const Assistant: React.FC<AssistantProps> = ({ merchantId, merchants }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentMerchant = merchants.find((m) => m.id === merchantId);

  // Clear chat when merchant changes
  useEffect(() => {
    setMessages([]);
    setInputText("");
    setIsLoading(false);
    setLastFailedMessage(null);
  }, [merchantId]);

  // Auto-scroll on new messages or loading state
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSendMessage = async (textToSend: string) => {
    const trimmed = textToSend.trim();
    if (!trimmed || isLoading) return;

    const userMsgId = `user_${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: "user",
      text: trimmed,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setIsLoading(true);
    setLastFailedMessage(null);

    try {
      const response = await sendAgentMessage(merchantId, trimmed);
      const assistantMsg: ChatMessage = {
        id: `assistant_${Date.now()}`,
        sender: "assistant",
        text: response.answer,
        tools_used: response.tools_used,
        mode: response.mode,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setLastFailedMessage(trimmed);
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: "assistant",
        text: `Error: ${err.message || "Failed to get response from assistant."}`,
        isError: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      // Focus back to input
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(inputText);
    }
  };

  const handleRetry = () => {
    if (lastFailedMessage) {
      handleSendMessage(lastFailedMessage);
    }
  };

  return (
    <div className="assistant-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">Merchant AI Partner</h1>
          <p className="view-subtitle">
            Plain-English answers backed by your digital transaction ledger ({currentMerchant?.name})
          </p>
        </div>
      </div>

      {/* Chat Messages Window */}
      <div className="chat-window">
        <div className="chat-messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat-empty-state">
              <div className="assistant-avatar-large">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h2 className="empty-state-title">Ask your AI Business Partner</h2>
              <p className="empty-state-text">
                Ask questions about your daily digital collections, volume vs ticket changes, or specific payment UTRs.
              </p>

              {/* 4 Prompt Chips */}
              <div className="prompt-chips-grid">
                {PROMPT_CHIPS.map((chip, index) => (
                  <button
                    key={index}
                    type="button"
                    className="prompt-chip-btn"
                    onClick={() => handleSendMessage(chip)}
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="5" y1="12" x2="19" y2="12" />
                      <polyline points="12 5 19 12 12 19" />
                    </svg>
                    <span>{chip}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className={`chat-message-row ${msg.sender}`}>
                <div className={`chat-bubble ${msg.sender} ${msg.isError ? "error" : ""}`}>
                  {/* Mode badge for assistant */}
                  {msg.sender === "assistant" && (msg.mode === "rule-based" || msg.mode === "template (AI answer rejected)") && (
                    <div className="rule-based-badge">
                      <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                        <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z" />
                      </svg>
                      {msg.mode === "rule-based"
                        ? "Rule-based mode (AI unavailable)"
                        : "Safety check replaced the AI answer"}
                    </div>
                  )}

                  {/* Message body rendered strictly as plain text (no HTML) */}
                  <div className="message-plain-text">{msg.text}</div>

                  {/* Tool execution breakdown under answer */}
                  {msg.tools_used && msg.tools_used.length > 0 && (
                    <div className="tools-used-section">
                      {msg.tools_used.map((tool, idx) => (
                        <details key={idx} className="tool-details-toggle">
                          <summary className="tool-summary-line">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                            </svg>
                            <span>Used: <strong>{tool.name}</strong></span>
                          </summary>
                          <pre className="tool-args-pre">
                            {JSON.stringify(tool.args, null, 2)}
                          </pre>
                        </details>
                      ))}
                    </div>
                  )}

                  {/* Inline Retry if error */}
                  {msg.isError && lastFailedMessage && (
                    <button
                      type="button"
                      className="btn-chat-retry"
                      onClick={handleRetry}
                      disabled={isLoading}
                    >
                      Retry Question
                    </button>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Typing Indicator */}
          {isLoading && (
            <div className="chat-message-row assistant">
              <div className="chat-bubble assistant typing-bubble">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-label">Analyzing transaction data...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="chat-input-container">
          <div className="chat-input-box">
            <input
              ref={inputRef}
              type="text"
              className="chat-input"
              placeholder="Ask a question about your digital collections..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
            />
            <button
              type="button"
              className="btn-send-message"
              onClick={() => handleSendMessage(inputText)}
              disabled={isLoading || !inputText.trim()}
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>

          {/* Footer sentence */}
          <div className="assistant-footer-notice">
            Numbers come from your transaction data. The AI only explains them.
          </div>
        </div>
      </div>
    </div>
  );
};

