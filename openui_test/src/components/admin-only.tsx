"use client";

import { useEffect, useState } from "react";
import { FileSpreadsheet, ShieldAlert } from "lucide-react";

import { DatasetUpload, isDatasetFile } from "@/components/dataset-upload";
import { useAsk } from "@/components/tools/shared";

/**
 * Admin-only pages (Data catalog, Prompt library, Agent map, Integrations).
 * The sidebar hides them for other users and the API returns 403, so this
 * only catches someone opening the route directly.
 */
export function AdminOnly({ role, children }: { role: string | null; children: React.ReactNode }) {
  if (role === null) return null; // user still loading
  if (role !== "admin") {
    return (
      <div className="qc-tool-page">
        <div className="qc-tool-page__inner">
          <div className="qc-state" role="alert">
            <ShieldAlert size={18} />
            <span>This page is for administrators. Ask an admin if you need access.</span>
          </div>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

/**
 * Drop an Excel/CSV file anywhere on the app to add it as a dataset
 * (admins). Opens the same preview-and-import flow as the Data catalog,
 * then offers to ask about the new data in a fresh chat.
 */
export function ChatFileDrop({ enabled }: { enabled: boolean }) {
  const ask = useAsk();
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let depth = 0;
    const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
    const onEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth += 1;
      setDragging(true);
    };
    const onLeave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onOver = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault();
    };
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      // A drop zone inside a page (Data catalog) handles its own drops.
      if ((event.target as HTMLElement | null)?.closest?.(".qc-dropzone")) {
        depth = 0;
        setDragging(false);
        return;
      }
      event.preventDefault();
      depth = 0;
      setDragging(false);
      const dropped = event.dataTransfer?.files?.[0];
      if (dropped && isDatasetFile(dropped)) setFile(dropped);
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [enabled]);

  useEffect(() => {
    if (!file) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setFile(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [file]);

  if (!enabled) return null;
  return (
    <>
      {dragging && !file && (
        <div className="qc-drop-overlay" aria-hidden="true">
          <div>
            <FileSpreadsheet size={34} />
            <strong>Drop to add as a dataset</strong>
            <span>Excel (.xlsx) or CSV · the chatbot can query it right after import</span>
          </div>
        </div>
      )}
      {file && (
        <div className="qc-modal" role="dialog" aria-modal="true" aria-label="Add a dataset" onClick={() => setFile(null)}>
          <div className="qc-modal__card" onClick={(event) => event.stopPropagation()}>
            <h2 className="qc-section-title"><FileSpreadsheet size={15} /> Add a dataset</h2>
            <DatasetUpload
              initialFile={file}
              onCancel={() => setFile(null)}
              onAsk={(result) => {
                setFile(null);
                ask(`Give me an overview of the ${result.name} collection with key statistics`);
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}
