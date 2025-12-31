import React, { useEffect, useState } from "react";
import { accountKey } from "../utils/accounts.js";

const API_BASE = "/api";

export default function DialogMessages({ account, selectedDialog, onSelectDialog, authToken, csrfToken }) {
  const [usernameInput, setUsernameInput] = useState("");
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    if (!account || !selectedDialog) {
      setMessages([]);
      return;
    }
    fetch(
      `${API_BASE}/accounts/${encodeURIComponent(
        accountKey(account)
      )}/dialogs/${encodeURIComponent(selectedDialog)}/messages`
      , {
        headers: {
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        credentials: "include",
      }
    )
      .then((res) => res.json())
      .then(setMessages)
      .catch(console.error);
  }, [account, selectedDialog, authToken]);

  const handleLoad = () => {
    if (!usernameInput || !account) return;
    onSelectDialog(usernameInput.trim());
  };

  return (
    <section className="dialog-messages">
      <h2>Dialog messages</h2>
      <div className="dialog-input">
        <input
          type="text"
          placeholder="Enter username"
          value={usernameInput}
          onChange={(e) => setUsernameInput(e.target.value)}
        />
        <button onClick={handleLoad}>Load</button>
      </div>
      <div className="dialog-history">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={
              "dialog-message " + (m.direction === "out" ? "dialog-out" : "dialog-in")
            }
          >
            <div className="dialog-meta">
              <span>{m.direction === "out" ? "You" : "Lead"}</span>
              <span>{m.ts}</span>
            </div>
            <div className="dialog-text">{m.text}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
