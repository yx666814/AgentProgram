import { type SyntheticEvent, useState } from "react";

import type { Task } from "../../api/backend-api";
import { Button } from "../../components/button";
import { useStageContext } from "./stage-context";

export function TaskQueue({
  canQueue,
  onCancel,
  onEnqueue,
  onStart,
  pendingTask,
}: {
  canQueue: boolean;
  onCancel: (task: Task) => Promise<void>;
  onEnqueue: (title: string) => Promise<void>;
  onStart: (task: Task) => Promise<void>;
  pendingTask: { id: string; eventType: string } | null;
}) {
  const { tasks } = useStageContext();
  const [title, setTitle] = useState("");
  const queued = tasks.filter(({ status }) => status === "queued");

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canQueue || title.trim() === "" || pendingTask !== null) {
      return;
    }
    await onEnqueue(title.trim());
  };

  return (
    <section className="data-panel task-panel" aria-labelledby="task-queue-title">
      <header><h2 id="task-queue-title">任务队列</h2><span>{String(tasks.length)} 项</span></header>
      <div className="task-list">
        {tasks.length === 0 ? <p className="empty-copy">当前阶段没有任务。</p> : null}
        {tasks.map((task) => {
          const queueIndex = queued.findIndex(({ id }) => id === task.id);
          return (
            <article className="task-item" key={task.id}>
              <div><strong>{task.title}</strong><span>{task.status}{queueIndex >= 0 ? ` · 队列 ${String(queueIndex + 1)}` : ""}</span></div>
              <div className="inline-actions">
                {task.status === "queued" ? <Button disabled={pendingTask !== null} onClick={() => void onStart(task)}>开始</Button> : null}
                {task.status === "queued" || task.status === "running" ? <Button disabled={pendingTask !== null} onClick={() => void onCancel(task)}>取消</Button> : null}
              </div>
            </article>
          );
        })}
      </div>
      <form className="task-composer" onSubmit={(event) => {
        void submit(event);
      }}>
        <input aria-label="新任务标题" disabled={!canQueue || pendingTask !== null} maxLength={200} onChange={(event) => {
          setTitle(event.target.value);
        }} placeholder={canQueue ? "输入新任务" : "只有当前活动阶段可以排队任务"} value={title} />
        <Button disabled={!canQueue || pendingTask !== null || title.trim() === ""} type="submit">加入队列</Button>
      </form>
      {pendingTask !== null ? <div className="event-wait">等待 {pendingTask.eventType} · {pendingTask.id}</div> : null}
    </section>
  );
}
