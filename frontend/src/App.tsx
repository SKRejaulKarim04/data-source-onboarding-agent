import { useCallback, useRef } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { Resizer } from "./components/Resizer";
import { ChatColumn } from "./components/chat/ChatColumn";
import { OutputPanel } from "./components/output/OutputPanel";
import { useHealth } from "./hooks/useHealth";
import { useOnboarding } from "./hooks/useOnboarding";
import { useResizer } from "./hooks/useResizer";
import { useViewportWidth } from "./hooks/useViewportWidth";
import { hasConnector } from "./api/types";

/** Defaults that match the CSS, used for the resizers' arithmetic. */
const SIDEBAR_DEFAULT = 250;
const SIDEBAR_MIN = 150;
const SIDEBAR_MAX = 420;
const CHAT_MIN = 320;
const OUTPUT_MIN = 300;
const HANDLE = 4;

export default function App() {
  const health = useHealth();
  const app = useOnboarding();
  const viewport = useViewportWidth();

  const sidebarRef = useRef<HTMLElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  // Each column is measured from its own left edge, so a drag stays exact no
  // matter what the column to its left is currently doing.
  const measureSidebar = useCallback(
    (clientX: number) =>
      clientX - (sidebarRef.current?.getBoundingClientRect().left ?? 0),
    [],
  );
  const measureChat = useCallback(
    (clientX: number) =>
      clientX - (chatRef.current?.getBoundingClientRect().left ?? 0),
    [],
  );

  const sidebarWidthNow = useCallback(
    () => sidebarRef.current?.getBoundingClientRect().width ?? SIDEBAR_DEFAULT,
    [],
  );
  const chatWidthNow = useCallback(
    () => chatRef.current?.getBoundingClientRect().width ?? CHAT_MIN,
    [],
  );

  const sidebar = useResizer({
    storageKey: "dsoa.sidebarWidth",
    min: SIDEBAR_MIN,
    max: SIDEBAR_MAX,
    measure: measureSidebar,
    currentWidth: sidebarWidthNow,
  });

  const sidebarWidth = sidebar.width ?? SIDEBAR_DEFAULT;
  const chatMax = Math.max(
    CHAT_MIN,
    viewport - sidebarWidth - OUTPUT_MIN - HANDLE * 2,
  );

  const chat = useResizer({
    storageKey: "dsoa.chatWidth",
    min: CHAT_MIN,
    max: chatMax,
    measure: measureChat,
    currentWidth: chatWidthNow,
  });

  const busy = app.pending !== null;

  return (
    <>
      <Header health={health} />

      <div className="app">
        <Sidebar
          ref={sidebarRef}
          width={sidebar.width}
          requests={app.requests}
          activeId={app.request?.id ?? null}
          onNewRequest={app.newRequest}
          onSelect={app.selectRequest}
          onDelete={app.deleteRequest}
        />

        <Resizer
          state={sidebar}
          label="Resize the request history"
          min={SIDEBAR_MIN}
          max={SIDEBAR_MAX}
          current={sidebarWidth}
        />

        <ChatColumn
          ref={chatRef}
          width={chat.width}
          messages={app.messages}
          prompt={app.prompt}
          busy={busy}
          generating={app.pending === "generate"}
          hasConnector={hasConnector(app.request?.connector)}
          onPromptChange={app.setPrompt}
          onSubmitPrompt={app.submitPrompt}
          onGenerate={app.generate}
          onAnswers={app.submitAnswers}
        />

        <Resizer
          state={chat}
          label="Resize the conversation"
          min={CHAT_MIN}
          max={chatMax}
          // Before the first drag the CSS owns the width (45%); report that
          // rather than the minimum, so screen readers announce the truth.
          current={chat.width ?? Math.round(viewport * 0.45)}
        />

        <OutputPanel
          request={app.request}
          activeTab={app.activeTab}
          testing={app.pending === "test"}
          onTabChange={app.setActiveTab}
          onTest={app.test}
        />
      </div>
    </>
  );
}
