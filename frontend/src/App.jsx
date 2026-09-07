import { useEffect, useState, useRef, useCallback } from "react";
import {
  createConversation,
  uploadPDF,
  askQuestion,
  getMessages,
  getConversations,
  deleteConversation,
  updateConversation,
  removePDF,
  getDocument,
} from "./services/api";
import Login from "./pages/Login";
import Register from "./pages/Register";
import {
  TbTrash,
  TbFileUpload,
  TbX,
  TbFile,
  TbPencil,
  TbCopy,
  TbCheck,
  TbMenu,
} from "react-icons/tb";

function App() {
  const fileInputRef = useRef(null);
  const copyTimeoutRef = useRef(null);

  const [authenticated, setAuthenticated] = useState(
    () => !!localStorage.getItem("token")
  );
  const [showRegister, setShowRegister] = useState(false);

  const [file, setFile] = useState(null);
  const [uploadedFilename, setUploadedFilename] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [loading, setLoading] = useState(false);

  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(
    () => localStorage.getItem("conversationId")
  );
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [status, setStatus] = useState("");

  const [copiedMessageIndex, setCopiedMessageIndex] = useState(null);

  const [editingConversationId, setEditingConversationId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [renaming, setRenaming] = useState(false);

  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!authenticated) return;

    let isMounted = true;

    const loadConversations = async () => {
      try {
        const data = await getConversations();
        if (isMounted) {
          setConversations(data.conversations || []);
        }
      } catch (error) {
        if (isMounted) {
          console.error("Failed to load conversations:", error);
        }
      }
    };

    loadConversations();

    return () => {
      isMounted = false;
    };
  }, [authenticated]);


  useEffect(() => {
    let isMounted = true;

    if (!authenticated || !conversationId) {
      return () => {
        isMounted = false;
      };
    }

    const loadMessages = async () => {
      try {
        const data = await getMessages(conversationId);
        if (isMounted) setMessages(data.messages || []);
      } catch (error) {
        if (isMounted) console.error(error);
      }
    };

    loadMessages();

    return () => {
      isMounted = false;
    };
  }, [authenticated, conversationId]);


  useEffect(() => {
    let isMounted = true;

    if (!conversationId) {
      return () => {
        isMounted = false;
      };
    }

    const loadDocument = async () => {
      try {
        const data = await getDocument(conversationId);
        if (isMounted) {
          setUploadedFilename(data.document?.filename || null);
        }
      } catch {
        if (isMounted) {
          setUploadedFilename(null);
        }
      }
    };

    loadDocument();

    return () => {
      isMounted = false;
    };
  }, [conversationId]);

  const handleLogout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_id");
    localStorage.removeItem("email");
    localStorage.removeItem("conversationId");

    setAuthenticated(false);
    setConversationId(null);
    setConversations([]);
    setMessages([]);
    setFile(null);
  }, []);

  const handleCreateConversation = async () => {
    try {
      setStatus("Creating conversation...");

      const data = await createConversation("New Legal Conversation");
      console.log("Conversation created:", data);

      setConversationId(data.id);
      localStorage.setItem("conversationId", data.id);

      setMessages([]);
      setFile(null);
      setUploadedFilename(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      setConversations((previous) => [
        {
          id: data.id,
          title: data.title,
          createdAt: data.createdAt,
          updatedAt: data.updatedAt,
        },
        ...previous,
      ]);

      setStatus("Conversation created successfully.");
      setSidebarOpen(false);
    } catch (error) {
      console.error("Conversation creation error:", error);
      setStatus(
        error.response?.data?.detail || "Failed to create conversation."
      );
    }
  };

  const handleSelectConversation = (id) => {
    if (id === conversationId) {
      setSidebarOpen(false);
      return;
    }
    setConversationId(id);
    localStorage.setItem("conversationId", id);
    setMessages([]);
    setQuestion("");
    setStatus("");
    setSidebarOpen(false);
  };


  const handleStartRename = (conversation) => {
    setEditingConversationId(conversation.id);
    setEditingTitle(conversation.title || "");
  };

  const handleCancelRename = () => {
    setEditingConversationId(null);
    setEditingTitle("");
  };

  const handleRenameConversation = async (targetId) => {
    const trimmedTitle = editingTitle.trim();
    if (!trimmedTitle) return;

    try {
      setRenaming(true);
      setStatus("Renaming conversation...");

      const data = await updateConversation(targetId, trimmedTitle);

      setConversations((previous) =>
        previous.map((conversation) =>
          conversation.id === targetId
            ? { ...conversation, title: data.title }
            : conversation
        )
      );

      setStatus("Conversation renamed successfully.");
      handleCancelRename();
    } catch (error) {
      console.error("Rename conversation error:", error);
      setStatus(
        error.response?.data?.detail || "Failed to rename conversation."
      );
    } finally {
      setRenaming(false);
    }
  };

  const handleRenameKeyDown = (event, id) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleRenameConversation(id);
    } else if (event.key === "Escape") {
      handleCancelRename();
    }
  };

  const handleDeleteConversation = async (id) => {
    try {
      setDeleting(true);
      setStatus("Deleting conversation...");

      await deleteConversation(id);

      setConversations((previous) =>
        previous.filter(
          (conversation) => conversation.id !== id
        )
      );

      if (conversationId === id) {
        setConversationId(null);
        setMessages([]);
        setQuestion("");

        localStorage.removeItem("conversationId");
      }

      setDeleteTarget(null);
      setStatus("");

    } catch (error) {
      console.error(
        "Delete conversation error:",
        error
      );

      setStatus(
        error.response?.data?.detail ||
        "Failed to delete conversation."
      );

    } finally {
      setDeleting(false);
    }
  };

  const handleFileChange = (event) => {
    const selectedFile = event.target.files?.[0];
    console.log("SELECTED FILE:", selectedFile);

    if (!selectedFile) {
      setFile(null);
      return;
    }

    setFile(selectedFile);
    setStatus(`Selected: ${selectedFile.name}`);
  };

  const handleUpload = async () => {
    console.log("Process PDF clicked");

    if (!conversationId) {
      setStatus("Please create a conversation first.");
      return;
    }

    if (!file) {
      setStatus("Please select a PDF first.");
      return;
    }

    try {
      setLoading(true);
      setStatus("Processing PDF...");

      console.log("Uploading:", file.name);
      console.log("Conversation ID:", conversationId);

      const data = await uploadPDF(conversationId, file);
      console.log("Upload response:", data);

      setUploadedFilename(file.name);
      setFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      setStatus(
        `PDF processed successfully. ${data.chunks} chunks created.`
      );
    } catch (error) {
      console.error("Upload error:", error);
      setStatus(
        error.response?.data?.detail || "PDF upload failed."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRemovePDF = async () => {
    if (!conversationId) return;

    const confirmed = window.confirm(
      "Remove this PDF? The conversation will no longer be able to answer from it."
    );

    if (!confirmed) return;

    try {
      setRemoving(true);
      setStatus("Removing document...");

      await removePDF(conversationId);

      setUploadedFilename(null);
      setFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      setStatus("Document removed successfully.");
    } catch (error) {
      console.error("Remove PDF error:", error);
      setStatus(
        error.response?.data?.detail || "Failed to remove document."
      );
    } finally {
      setRemoving(false);
    }
  };

  const handleCopyAnswer = async (content, index) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageIndex(index);

      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }

      copyTimeoutRef.current = setTimeout(() => {
        setCopiedMessageIndex(null);
      }, 2000);
    } catch (error) {
      console.error("Failed to copy answer:", error);
    }
  };

  const handleAsk = async () => {
    console.log("Ask button clicked");

    if (!question.trim()) {
      setStatus("Please enter a question.");
      return;
    }

    if (!conversationId) {
      setStatus("No conversation ID.");
      return;
    }

    try {
      setAsking(true);
      setStatus("Analyzing document...");

      console.log("Question:", question);

      const data = await askQuestion(conversationId, question);
      console.log("Answer:", data);

      setMessages((previous) => [
        ...previous,
        {
          role: "user",
          content: question,
        },
        {
          role: "assistant",
          content: data.response,
        },
      ]);

      setQuestion("");
      setStatus("");
    } catch (error) {
      console.error("Question error:", error);
      setStatus(
        error.response?.data?.detail || "Failed to get answer."
      );
    } finally {
      setAsking(false);
    }
  };

  if (!authenticated) {
    if (showRegister) {
      return (
        <Register
          onRegistered={() => setShowRegister(false)}
          onLoginClick={() => setShowRegister(false)}
        />
      );
    }

    return (
      <Login
        onLoggedIn={() => setAuthenticated(true)}
        onRegisterClick={() => setShowRegister(true)}
      />
    );
  }

  return (
    <div className="min-h-screen bg-docket-bg text-docket-text font-sans">

      <>
        {/* Overlay */}
        {sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-40 bg-black/50"
          />
        )}

        {/* Sidebar */}
        <aside
          className={`
      fixed top-0 left-0 z-50
      h-full w-72
      bg-docket-bg
      border-r border-docket-border
      p-5
      flex flex-col
      transform transition-transform duration-300 ease-in-out
      ${sidebarOpen
              ? "translate-x-0"
              : "-translate-x-full"
            }
    `}
        >

          {/* Sidebar Header */}
          <div className="flex items-start justify-between mb-8">

            <div>
              <p className="text-[11px] tracking-[0.2em] text-docket-muted uppercase mb-1">
                Legal RAG Assistant
              </p>
            </div>

            <button
              onClick={() => setSidebarOpen(false)}
              aria-label="Close sidebar"
              title="Close"
              className="text-docket-muted hover:text-docket-text transition-colors cursor-pointer"
            >
              <TbX className="text-xl" />
            </button>

          </div>

          {/* New Conversation */}
          <button
            onClick={handleCreateConversation}
            className="w-full mb-3 px-4 py-2.5 rounded-md bg-docket-accent text-docket-bg text-sm font-medium hover:bg-docket-accent-hover transition-colors flex items-center justify-center gap-2 cursor-pointer"
          >
            <span className="text-base leading-none">
              +
            </span>

            Open new matter
          </button>

          {/* Logout */}
          <button
            onClick={handleLogout}
            className="w-full mb-6 px-4 py-2.5 rounded-md border border-docket-border text-sm text-docket-subtext hover:border-docket-border-subtle hover:text-docket-text transition-colors cursor-pointer"
          >
            Log out
          </button>

          {/* Conversations */}
          <div className="flex-1 overflow-y-auto space-y-1">

            {conversations.length === 0 && (
              <p className="text-sm text-docket-muted leading-relaxed px-1 pt-4">
                No matters open yet. Start one to upload a document and begin asking questions.
              </p>
            )}

            {conversations.map((conversation, i) => (
              <div
                key={conversation.id}
                className={`group flex items-center gap-2 rounded-md border-l-2 ${conversation.id === conversationId
                  ? "border-l-docket-accent bg-docket-card"
                  : "border-l-transparent hover:bg-docket-card/60"
                  }`}
              >

                {editingConversationId === conversation.id ? (

                  <div className="flex-1 min-w-0 px-3 py-2">

                    <p className="text-[11px] font-mono text-docket-muted mb-1">
                      No. {String(i + 1).padStart(3, "0")}
                    </p>

                    <input
                      autoFocus
                      value={editingTitle}
                      onChange={(event) =>
                        setEditingTitle(event.target.value)
                      }
                      onKeyDown={(event) =>
                        handleRenameKeyDown(
                          event,
                          conversation.id
                        )
                      }
                      maxLength={100}
                      disabled={renaming}
                      className="w-full bg-docket-bg border border-docket-accent rounded px-2 py-1 text-sm text-docket-text focus:outline-none"
                    />

                    <div className="flex gap-3 mt-2">

                      <button
                        onClick={() =>
                          handleRenameConversation(
                            conversation.id
                          )
                        }
                        disabled={renaming}
                        className="text-xs text-docket-accent hover:text-docket-accent-hover disabled:opacity-50 cursor-pointer"
                      >
                        {renaming ? "Saving..." : "Save"}
                      </button>

                      <button
                        onClick={handleCancelRename}
                        disabled={renaming}
                        className="text-xs text-docket-muted hover:text-docket-text cursor-pointer"
                      >
                        Cancel
                      </button>

                    </div>

                  </div>

                ) : (

                  <>
                    <button
                      onClick={() =>
                        handleSelectConversation(
                          conversation.id
                        )
                      }
                      className="flex-1 text-left pl-3 pr-2 py-3 min-w-0 cursor-pointer"
                    >

                      <p className="text-[11px] font-mono text-docket-muted mb-0.5">
                        No. {String(i + 1).padStart(3, "0")}
                      </p>

                      <p className="text-sm text-docket-text truncate">
                        {conversation.title}
                      </p>

                    </button>

                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        handleStartRename(conversation);
                      }}
                      aria-label="Rename conversation"
                      title="Rename matter"
                      className="px-1 py-3 text-docket-muted hover:text-docket-accent opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    >
                      <TbPencil className="text-base" />
                    </button>

                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteTarget(conversation);
                      }}
                      aria-label="Delete conversation"
                      title="Delete matter"
                      className="px-3 py-3 text-docket-muted hover:text-docket-danger opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    >
                      <TbTrash className="text-base" />
                    </button>
                  </>

                )}

              </div>
            ))}

          </div>

        </aside>
      </>

      <main className="flex-1 overflow-y-auto">

        <button
          onClick={() => setSidebarOpen(true)}
          aria-label="Open sidebar"
          title="Open conversations"
          className="fixed top-5 left-5 z-30 flex items-center justify-center w-10 h-10 rounded-lg bg-docket-card border border-docket-border text-docket-muted hover:text-docket-text hover:border-docket-border-subtle transition-colors cursor-pointer"
        >
          <TbMenu className="text-xl" />
        </button>

        <div className="max-w-3xl mx-auto py-12">
          <header className="mb-2 p-4">
            <h1 className="font-serif text-3xl text-docket-heading mb-2">
              Legal RAG Assistant
            </h1>
            <p className="text-docket-subtext-muted">
              Upload a legal PDF, then ask questions grounded in its text.
            </p>
          </header>

          <section className="bg-docket-card border border-docket-border p-6 mb-6">
            <h2 className="font-serif text-lg text-docket-heading mb-4">
              Exhibit A — document intake
            </h2>

            <label className="flex items-center justify-between border border-dashed border-docket-border-subtle rounded-lg px-4 py-4 cursor-pointer hover:border-docket-accent transition-colors">
              <span className="flex items-center gap-3 text-sm text-docket-subtext">
                <TbFileUpload className="text-lg" />
                {file ? file.name : "Choose a PDF to upload"}
              </span>
              <span className="text-xs text-docket-muted font-mono">.pdf</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                onChange={handleFileChange}
                className="hidden"
              />
            </label>

            <button
              onClick={handleUpload}
              disabled={!file || loading}
              className="mt-4 px-5 py-2.5 rounded-md bg-docket-accent text-docket-bg text-sm font-medium hover:bg-docket-accent-hover disabled:bg-docket-border disabled:text-docket-muted transition-colors cursor-pointer"
            >
              {loading ? "Processing document..." : "Process PDF"}
            </button>

            {uploadedFilename && (
              <div className="mt-4 flex items-center gap-3 bg-docket-bg border border-docket-border rounded-lg px-4 py-3">
                <TbFile className="text-docket-accent text-lg shrink-0" />
                <span className="text-sm text-docket-text truncate flex-1">
                  {uploadedFilename}
                </span>
                <button
                  onClick={handleRemovePDF}
                  disabled={removing}
                  title="Remove PDF"
                  className="flex items-center gap-1 text-xs text-docket-muted hover:text-docket-danger transition-colors shrink-0 disabled:opacity-50 cursor-pointer"
                >
                  <TbX className="text-base" />
                  <span>{removing ? "Removing..." : "Remove"}</span>
                </button>
              </div>
            )}

            {status && (
              <p className="mt-3 text-sm text-docket-subtext border-l-2 border-docket-border-subtle pl-3">
                {status}
              </p>
            )}
          </section>

          {/* Q&A PANEL */}
          <section className="bg-docket-card border border-docket-border p-4">
            <h2 className="font-serif text-lg text-docket-heading mb-4">
              Examination
            </h2>

            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask something about your document..."
              className="w-full h-28 bg-docket-bg border border-docket-border rounded-lg p-4 text-docket-text placeholder:text-docket-placeholder focus:outline-none focus:border-docket-accent resize-none"
            />

            <button
              onClick={handleAsk}
              disabled={!question.trim() || asking}
              className="mt-3 px-5 py-2.5 rounded-md border border-docket-accent text-docket-accent text-sm font-medium hover:bg-docket-accent hover:text-docket-bg disabled:opacity-40 disabled:pointer-events-none transition-colors cursor-pointer"
            >
              {asking ? "Reviewing document..." : "Ask question"}
            </button>

            {messages.length === 0 ? (
              <p className="mt-8 text-sm text-docket-muted text-center py-6 border-t border-docket-border">
                Your exchange will appear here once you ask a question.
              </p>
            ) : (
              <div className="mt-8 space-y-4 pt-6 border-t border-docket-border">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={
                      message.role === "user"
                        ? "pl-4 border-l-2 border-docket-border-subtle"
                        : "bg-docket-accent text-docket-accent-dark rounded-lg p-4"
                    }
                  >

                    {message.role === "assistant" ? (
                      <>
                        {/* Answer header */}
                        <div className="flex items-center justify-between mb-2">

                          <p className="text-[11px] font-mono uppercase tracking-wide text-docket-card">
                            Finding
                          </p>

                          <button
                            onClick={() =>
                              handleCopyAnswer(
                                message.content,
                                index
                              )
                            }
                            title={
                              copiedMessageIndex === index
                                ? "Copied"
                                : "Copy answer"
                            }
                            aria-label="Copy answer"
                            className="flex items-center justify-center w-7 h-7 rounded-md text-docket-accent-dark/60 hover:text-docket-accent-dark hover:bg-docket-accent-dark/10 transition-colors cursor-pointer"
                          >
                            {copiedMessageIndex === index ? (
                              <TbCheck className="text-base" />
                            ) : (
                              <TbCopy className="text-base" />
                            )}
                          </button>

                        </div>

                        {/* Answer */}
                        <div className="whitespace-pre-wrap leading-relaxed font-serif">
                          {message.content}
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Question */}
                        <p className="text-[11px] font-mono uppercase tracking-wide mb-2 text-docket-muted">
                          Question
                        </p>

                        <div className="whitespace-pre-wrap leading-relaxed text-docket-text">
                          {message.content}
                        </div>
                      </>
                    )}

                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      {deleteTarget && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => {
            if (!deleting) {
              setDeleteTarget(null);
            }
          }}
        >

          <div
            className="w-full max-w-md bg-docket-card border border-docket-border rounded-xl shadow-2xl p-3"
            onClick={(event) => event.stopPropagation()}
          >

            {/* Header */}
            <div className="flex items-start justify-between">

              <div>
                <h2 className="font-serif text-xl text-docket-heading">
                  Delete matter?
                </h2>
              </div>

              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                aria-label="Close"
                className="text-docket-muted hover:text-docket-text transition-colors cursor-pointer disabled:opacity-50"
              >
                <TbX className="text-xl" />
              </button>

            </div>

            {/* Conversation name */}
            <div className="mt-5 rounded-lg bg-docket-bg border border-docket-border px-4 py-3">

              <p className="text-[11px] font-mono text-docket-muted uppercase tracking-wide mb-1">
                Matter
              </p>

              <p className="text-sm text-docket-text truncate">
                {deleteTarget.title}
              </p>

            </div>

            {/* Warning */}
            <div className="mt-4 border-l-2 border-docket-danger pl-3">

              <p className="text-sm text-docket-subtext-muted leading-relaxed">
                This will permanently delete the conversation,
                its messages, and the uploaded document.
                This action cannot be undone.
              </p>

            </div>

            {/* Buttons */}
            <div className="flex justify-end gap-3 mt-6">

              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2.5 rounded-md border border-docket-border text-sm text-docket-subtext hover:border-docket-border-subtle hover:text-docket-text transition-colors cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                onClick={() =>
                  handleDeleteConversation(
                    deleteTarget.id
                  )
                }
                disabled={deleting}
                className="px-4 py-2.5 rounded-md bg-docket-danger text-white text-sm font-medium hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
              >
                {deleting ? "Deleting..." : "Delete matter"}
              </button>

            </div>

          </div>

        </div>
      )}
    </div>
  );
}

export default App;