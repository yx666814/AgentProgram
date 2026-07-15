import { type SyntheticEvent, useState } from "react";

import { Button } from "../../components/button";
import { useStageContext } from "./stage-context";

export function MessageStream({
  canWrite,
  onSend,
  pendingMessageId,
}: {
  canWrite: boolean;
  onSend: (content: string, correctionOfId: string | null) => Promise<void>;
  pendingMessageId: string | null;
}) {
  const { messages, room } = useStageContext();
  const [draft, setDraft] = useState("");
  const [correctionOfId, setCorrectionOfId] = useState<string | null>(null);

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft.trim() === "" || !canWrite || pendingMessageId !== null) {
      return;
    }
    await onSend(draft.trim(), correctionOfId);
  };

  return (
    <section className="data-panel message-panel" aria-labelledby="message-stream-title">
      <header>
        <h2 id="message-stream-title">消息</h2>
        <span>{room.status === "consultation" ? "只读阶段咨询" : "当前 Room"}</span>
      </header>
      <div className="message-history">
        {messages.length === 0 ? <p className="empty-copy">这个阶段 Room 还没有持久化消息。</p> : null}
        {messages.map((message) => (
          <article className={`message-item message-${message.author}`} key={message.id}>
            <header><strong>{message.author}</strong><span>#{String(message.sequence)} · {message.kind}</span></header>
            <p>{message.content}</p>
            {message.correction_of_id !== null && message.correction_of_id !== undefined ? <small>更正自 {message.correction_of_id}</small> : null}
            {canWrite ? (
              <Button onClick={() => {
                setCorrectionOfId(message.id);
              }} tone="ghost">更正此消息</Button>
            ) : null}
          </article>
        ))}
      </div>
      <form className="message-composer" onSubmit={(event) => {
        void submit(event);
      }}>
        {correctionOfId !== null ? (
          <div className="correction-banner">正在创建对 {correctionOfId} 的更正<Button onClick={() => {
            setCorrectionOfId(null);
          }} tone="ghost">取消</Button></div>
        ) : null}
        <textarea
          aria-label="阶段消息"
          disabled={!canWrite || pendingMessageId !== null}
          onChange={(event) => {
            setDraft(event.target.value);
          }}
          placeholder={canWrite ? "发送到当前阶段 Room" : "当前阶段不可写"}
          rows={3}
          value={draft}
        />
        <div className="page-actions">
          {pendingMessageId !== null ? <span className="event-wait">等待 message.appended · {pendingMessageId}</span> : null}
          <Button disabled={!canWrite || pendingMessageId !== null || draft.trim() === ""} tone="primary" type="submit">发送</Button>
        </div>
      </form>
    </section>
  );
}
