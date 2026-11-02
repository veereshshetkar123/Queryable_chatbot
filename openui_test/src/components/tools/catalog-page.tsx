"use client";

import { useState } from "react";
import { Database, FileSpreadsheet, Hash, Pencil, Plus, Search, Table2, Trash2, Type, X } from "lucide-react";

import { DatasetUpload } from "@/components/dataset-upload";
import { AskButton, LoadState, ToolPage, useApi, useAsk } from "@/components/tools/shared";
import { authFetch, errorMessage } from "@/lib/api";

type Field = { name: string; type: string; samples: Record<string, unknown>[] };
type DatasetMeta = {
  label: string | null;
  description: string;
  filename: string | null;
  sheet: string | null;
  uploaded_by: string | null;
  uploaded_at: string | null;
  rows: number | null;
};
type Collection = { name: string; documents: number; source: "upload" | "sample"; dataset: DatasetMeta | null; fields: Field[] };

const NUMERIC = new Set(["int", "float", "Int64", "Decimal128"]);

function sampleText(field: Field) {
  return field.samples
    .map((sample) => sample[field.name])
    .filter((value) => value != null)
    .map((value) => (typeof value === "object" ? JSON.stringify(value) : String(value)))
    .slice(0, 3)
    .join(" · ");
}

function when(iso: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function EditDataset({ collection, onSaved, onClose }: { collection: Collection; onSaved: () => void; onClose: () => void }) {
  const [label, setLabel] = useState(collection.dataset?.label ?? "");
  const [description, setDescription] = useState(collection.dataset?.description ?? "");
  const [error, setError] = useState("");
  const save = async () => {
    const response = await authFetch(`/api/catalog/${encodeURIComponent(collection.name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, description }),
    });
    if (!response.ok) {
      setError(await errorMessage(response, "Could not save."));
      return;
    }
    onSaved();
    onClose();
  };
  return (
    <form
      className="qc-catalog__edit"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Display name" maxLength={80} aria-label="Display name" />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} maxLength={500} placeholder="Description" aria-label="Description" />
      {error && <p className="qc-upload__error">{error}</p>}
      <div className="qc-upload__actions">
        <button type="button" className="qc-ghost-button" onClick={onClose}>Cancel</button>
        <button type="submit" className="qc-primary-button">Save</button>
      </div>
    </form>
  );
}

export function CatalogPage() {
  const { data, error, loading, reload } = useApi<{ collections: Collection[] }>("/api/catalog");
  const ask = useAsk();
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const needle = filter.trim().toLowerCase();
  const all = data?.collections ?? [];
  const collections = all.filter(
    (c) =>
      !needle ||
      c.name.toLowerCase().includes(needle) ||
      (c.dataset?.label ?? "").toLowerCase().includes(needle) ||
      c.fields.some((f) => f.name.toLowerCase().includes(needle)),
  );
  const uploads = all.filter((c) => c.source === "upload").length;
  const rows = all.reduce((sum, c) => sum + c.documents, 0);

  const remove = async (collection: Collection) => {
    if (!window.confirm(`Delete the dataset "${collection.dataset?.label ?? collection.name}" and its ${collection.documents.toLocaleString()} rows? This cannot be undone.`)) return;
    setActionError("");
    const response = await authFetch(`/api/catalog/${encodeURIComponent(collection.name)}`, { method: "DELETE" });
    if (!response.ok) setActionError(await errorMessage(response, "The dataset could not be deleted."));
    reload();
  };

  return (
    <ToolPage
      icon={<Database size={13} />}
      eyebrow="Data catalog · Admin"
      title="Data the chatbot can read"
      description="Every collection and field the chatbot is allowed to query. Add a dataset by uploading an Excel or CSV file; sample values are PII-masked."
      actions={
        <button type="button" className="qc-primary-button" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          {adding ? <X size={15} /> : <Plus size={15} />} {adding ? "Close" : "Add dataset"}
        </button>
      }
    >
      <div className="qc-kpi-row qc-catalog__stats">
        <div className="qc-kpi"><span className="qc-kpi__label">Collections</span><strong className="qc-kpi__value">{all.length}</strong></div>
        <div className="qc-kpi"><span className="qc-kpi__label">Uploaded datasets</span><strong className="qc-kpi__value">{uploads}</strong></div>
        <div className="qc-kpi"><span className="qc-kpi__label">Rows</span><strong className="qc-kpi__value">{rows.toLocaleString()}</strong></div>
      </div>

      {adding && (
        <section className="qc-tile qc-catalog__add" aria-label="Add a dataset">
          <h2 className="qc-section-title"><FileSpreadsheet size={15} /> Add a dataset</h2>
          <DatasetUpload
            onDone={() => reload()}
            onAsk={(result) => ask(`Give me an overview of the ${result.name} collection with key statistics`)}
          />
        </section>
      )}

      <label className="qc-search">
        <Search size={15} />
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter collections or fields…" />
      </label>
      {actionError && <p className="qc-upload__error" role="alert">{actionError}</p>}
      <LoadState loading={loading} error={error} onRetry={reload} />
      <div className="qc-catalog">
        {collections.map((collection) => (
          <article key={collection.name} className="qc-tile qc-catalog__item" data-source={collection.source}>
            <header className="qc-tile__head">
              <h2 className="qc-tile__title">
                <Table2 size={15} /> {collection.dataset?.label ?? collection.name}
              </h2>
              <span className="qc-pill">{collection.documents.toLocaleString()} rows</span>
            </header>
            <div className="qc-catalog__meta">
              <code>{collection.name}</code>
              <span className={`qc-catalog__badge qc-catalog__badge--${collection.source}`}>
                {collection.source === "upload" ? "Uploaded" : "Built-in"}
              </span>
              {collection.dataset && (
                <span className="qc-muted">
                  {collection.dataset.filename} · {collection.dataset.uploaded_by} · {when(collection.dataset.uploaded_at)}
                </span>
              )}
            </div>
            {collection.dataset?.description && editing !== collection.name && (
              <p className="qc-catalog__desc">{collection.dataset.description}</p>
            )}
            {editing === collection.name && (
              <EditDataset collection={collection} onSaved={reload} onClose={() => setEditing(null)} />
            )}
            <ul className="qc-catalog__fields">
              {collection.fields.map((field) => (
                <li key={field.name} className={needle && field.name.toLowerCase().includes(needle) ? "is-match" : ""}>
                  <span className="qc-catalog__type" title={field.type}>
                    {NUMERIC.has(field.type) ? <Hash size={12} /> : <Type size={12} />}
                  </span>
                  <code>{field.name}</code>
                  <span className="qc-catalog__sample">{sampleText(field)}</span>
                </li>
              ))}
            </ul>
            <footer className="qc-catalog__foot">
              {collection.source === "upload" && (
                <>
                  <button type="button" className="qc-ghost-button" onClick={() => setEditing(collection.name)}>
                    <Pencil size={13} /> Edit
                  </button>
                  <button type="button" className="qc-ghost-button qc-ghost-button--danger" onClick={() => void remove(collection)}>
                    <Trash2 size={13} /> Delete
                  </button>
                </>
              )}
              <AskButton prompt={`Give me an overview of the ${collection.name} collection with key statistics`} label="Overview" />
            </footer>
          </article>
        ))}
      </div>
    </ToolPage>
  );
}
