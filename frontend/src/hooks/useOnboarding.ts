import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import {
  hasConnector,
  hasExtraction,
  hasSandbox,
  type OnboardingRequest,
  type RequestSummary,
} from "../api/types";
import { messageId, type ChatMessage } from "../types/chat";
import type { TabKey } from "../components/output/OutputPanel";

/** Which call is in flight. One at a time, by design — the pipeline is a chain. */
export type Pending = null | "extract" | "answers" | "generate" | "test";

export interface Onboarding {
  request: OnboardingRequest | null;
  requests: RequestSummary[];
  messages: ChatMessage[];
  prompt: string;
  pending: Pending;
  activeTab: TabKey;
  setPrompt: (value: string) => void;
  setActiveTab: (tab: TabKey) => void;
  submitPrompt: () => void;
  submitAnswers: (answers: Record<string, string>) => void;
  generate: () => void;
  test: (credentials: Record<string, string>) => void;
  selectRequest: (id: string) => void;
  deleteRequest: (id: string) => void;
  newRequest: () => void;
}

/**
 * All of the app's behaviour in one place.
 *
 * The server payload is the single source of truth for *state*; the chat thread
 * is a log of how that state was reached. Every action therefore does the same
 * two things: replace `request` with what the API returned, and append the
 * bubbles describing it.
 */
export function useOnboarding(): Onboarding {
  const [request, setRequest] = useState<OnboardingRequest | null>(null);
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState<Pending>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("checks");

  // Read inside callbacks instead of closing over state, so a handler created
  // on an earlier render can never act on an earlier request.
  const requestRef = useRef<OnboardingRequest | null>(null);
  requestRef.current = request;
  const pendingRef = useRef<Pending>(null);
  pendingRef.current = pending;

  const append = useCallback((...added: ChatMessage[]) => {
    setMessages((current) => [...current, ...added]);
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setRequests(await api.listRequests());
    } catch {
      // The history strip is not worth interrupting the conversation for.
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  /** Extraction always produces a card, and questions when the spec is thin. */
  const appendExtraction = useCallback(
    (payload: OnboardingRequest) => {
      const extraction = payload.extraction;
      if (!hasExtraction(extraction)) return;

      const added: ChatMessage[] = [
        { id: messageId("ex"), role: "agent", kind: "extraction", extraction },
      ];
      if (extraction.questions.length > 0) {
        added.push({
          id: messageId("q"),
          role: "agent",
          kind: "questions",
          questions: extraction.questions,
        });
      }
      append(...added);
    },
    [append],
  );

  const fail = useCallback(
    (label: string, error: unknown) => {
      const detail =
        error instanceof ApiError ? error.message : "Unexpected error";
      append({
        id: messageId("err"),
        role: "agent",
        kind: "error",
        text: `${label}: ${detail}`,
      });
    },
    [append],
  );

  const submitPrompt = useCallback(() => {
    const text = prompt.trim();
    if (!text || pendingRef.current) return;

    append({ id: messageId("u"), role: "user", kind: "text", text });
    setPrompt("");
    setPending("extract");

    api
      .createRequest(text)
      .then((payload) => {
        setRequest(payload);
        appendExtraction(payload);
        setActiveTab("checks");
        void refreshHistory();
      })
      .catch((error) => fail("Extraction failed", error))
      .finally(() => setPending(null));
  }, [prompt, append, appendExtraction, fail, refreshHistory]);

  const submitAnswers = useCallback(
    (answers: Record<string, string>) => {
      const current = requestRef.current;
      if (!current || pendingRef.current) return;

      const text = Object.entries(answers)
        .map(([field, value]) => `${field}: ${value}`)
        .join("\n");
      append({ id: messageId("u"), role: "user", kind: "text", text });
      setPending("answers");

      api
        .submitAnswers(current.id, answers)
        .then((payload) => {
          setRequest(payload);
          appendExtraction(payload);
          void refreshHistory();
        })
        .catch((error) => fail("Could not apply answers", error))
        .finally(() => setPending(null));
    },
    [append, appendExtraction, fail, refreshHistory],
  );

  const generate = useCallback(() => {
    const current = requestRef.current;
    if (!current || pendingRef.current) return;

    append({
      id: messageId("u"),
      role: "user",
      kind: "text",
      text: "Generate the connector",
    });
    setPending("generate");

    api
      .generate(current.id)
      .then((payload) => {
        setRequest(payload);
        if (hasConnector(payload.connector)) {
          append({
            id: messageId("gen"),
            role: "agent",
            kind: "connector",
            accepted: payload.connector.accepted,
            summary: payload.connector.summary,
          });
        }
        setActiveTab("checks");
        void refreshHistory();
      })
      .catch((error) => fail("Generation failed", error))
      .finally(() => setPending(null));
  }, [append, fail, refreshHistory]);

  const test = useCallback(
    (credentials: Record<string, string>) => {
      const current = requestRef.current;
      if (!current || pendingRef.current) return;

      setPending("test");
      api
        .testConnection(current.id, credentials)
        .then((payload) => {
          setRequest(payload);
          if (hasSandbox(payload.sandbox)) {
            append({
              id: messageId("test"),
              role: "agent",
              kind: "sandbox",
              success: payload.sandbox.success,
              summary: payload.sandbox.summary,
            });
          }
          setActiveTab("connect");
          void refreshHistory();
        })
        .catch((error) => fail("Connection test failed", error))
        .finally(() => setPending(null));
    },
    [append, fail, refreshHistory],
  );

  const newRequest = useCallback(() => {
    setRequest(null);
    setMessages([]);
    setPrompt("");
    setActiveTab("checks");
    void refreshHistory();
  }, [refreshHistory]);

  const selectRequest = useCallback(
    (id: string) => {
      if (pendingRef.current) return;

      api
        .getRequest(id)
        .then((payload) => {
          setRequest(payload);
          setMessages(replay(payload));
          setActiveTab("checks");
          void refreshHistory();
        })
        .catch((error) => fail("Could not load request", error));
    },
    [fail, refreshHistory],
  );

  const deleteRequest = useCallback(
    (id: string) => {
      api
        .deleteRequest(id)
        .then(() => {
          if (requestRef.current?.id === id) newRequest();
          void refreshHistory();
        })
        .catch((error) => fail("Could not delete request", error));
    },
    [fail, newRequest, refreshHistory],
  );

  return {
    request,
    requests,
    messages,
    prompt,
    pending,
    activeTab,
    setPrompt,
    setActiveTab,
    submitPrompt,
    submitAnswers,
    generate,
    test,
    selectRequest,
    deleteRequest,
    newRequest,
  };
}

/**
 * Rebuild a thread from a stored request.
 *
 * The server keeps the state, not the conversation, so this reconstructs the
 * shortest history consistent with what it returned. Answers given earlier are
 * folded into the draft and do not reappear as separate turns.
 */
function replay(payload: OnboardingRequest): ChatMessage[] {
  const thread: ChatMessage[] = [
    { id: messageId("u"), role: "user", kind: "text", text: payload.prompt },
  ];

  const extraction = payload.extraction;
  if (hasExtraction(extraction)) {
    thread.push({
      id: messageId("ex"),
      role: "agent",
      kind: "extraction",
      extraction,
    });
    if (
      extraction.questions.length > 0 &&
      payload.status === "needs_clarification"
    ) {
      thread.push({
        id: messageId("q"),
        role: "agent",
        kind: "questions",
        questions: extraction.questions,
      });
    }
  }

  if (hasConnector(payload.connector)) {
    thread.push({
      id: messageId("gen"),
      role: "agent",
      kind: "connector",
      accepted: payload.connector.accepted,
      summary: payload.connector.summary,
    });
  }

  if (hasSandbox(payload.sandbox)) {
    thread.push({
      id: messageId("test"),
      role: "agent",
      kind: "sandbox",
      success: payload.sandbox.success,
      summary: payload.sandbox.summary,
    });
  }

  return thread;
}
