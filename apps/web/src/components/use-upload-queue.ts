"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiErrorOf } from "@/lib/api";
import {
  uploadDocument,
  validateUploadFile,
  type DocumentType,
  type UploadResult,
} from "@/lib/documents";

export const MAX_CONCURRENT_UPLOADS = 3;

const READ_ONLY_CODES = new Set(["revision_read_only", "archived_project", "cancelled_project"]);

export type UploadItemStatus = "queued" | "uploading" | "done" | "failed";

export type UploadItem = {
  id: number;
  file: File;
  documentType: DocumentType;
  status: UploadItemStatus;
  progress: number;
  error: string | null;
  errorCode: string | null;
  duplicate: boolean;
  retryable: boolean;
};

type Options = {
  projectId: string;
  revisionId: string;
  onUploaded?: (result: UploadResult) => void;
  /** Called when the server says the revision or project can no longer be changed. */
  onReadOnly?: (message: string) => void;
};

export function useUploadQueue({ projectId, revisionId, onUploaded, onReadOnly }: Options) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const controllers = useRef(new Map<number, AbortController>());
  const nextId = useRef(1);
  const callbacks = useRef({ onUploaded, onReadOnly });
  callbacks.current = { onUploaded, onReadOnly };

  const patch = useCallback((id: number, changes: Partial<UploadItem>) => {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...changes } : item)));
  }, []);

  const run = useCallback(
    async (item: UploadItem, controller: AbortController) => {
      try {
        const result = await uploadDocument(
          projectId,
          revisionId,
          item.file,
          item.documentType === "UNKNOWN" ? {} : { document_type: item.documentType },
          {
            signal: controller.signal,
            onProgress: (progress) => patch(item.id, { progress }),
          },
        );
        patch(item.id, {
          status: "done",
          progress: 100,
          duplicate: result.duplicate_detected,
          error: null,
          errorCode: null,
        });
        callbacks.current.onUploaded?.(result);
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        const { code, detail } = apiErrorOf(err);
        if (code && READ_ONLY_CODES.has(code)) {
          setItems((current) =>
            current.map((candidate) =>
              candidate.id === item.id || candidate.status === "queued"
                ? {
                    ...candidate,
                    status: "failed",
                    error: detail,
                    errorCode: code,
                    retryable: false,
                  }
                : candidate,
            ),
          );
          callbacks.current.onReadOnly?.(detail);
        } else {
          patch(item.id, { status: "failed", error: detail, errorCode: code, retryable: true });
        }
      } finally {
        controllers.current.delete(item.id);
      }
    },
    [projectId, revisionId, patch],
  );

  useEffect(() => {
    const uploading = items.filter((item) => item.status === "uploading").length;
    const free = MAX_CONCURRENT_UPLOADS - uploading;
    if (free <= 0) {
      return;
    }
    const next = items
      .filter((item) => item.status === "queued" && !controllers.current.has(item.id))
      .slice(0, free);
    for (const item of next) {
      const controller = new AbortController();
      controllers.current.set(item.id, controller);
      patch(item.id, { status: "uploading", progress: 0, error: null, errorCode: null });
      void run(item, controller);
    }
  }, [items, patch, run]);

  useEffect(() => {
    const active = controllers.current;
    return () => {
      for (const controller of active.values()) {
        controller.abort();
      }
      active.clear();
    };
  }, []);

  const add = useCallback((files: File[], documentType: DocumentType) => {
    const added: UploadItem[] = files.map((file) => {
      const problem = validateUploadFile(file);
      return {
        id: nextId.current++,
        file,
        documentType,
        status: problem ? "failed" : "queued",
        progress: 0,
        error: problem,
        errorCode: problem ? "client_validation" : null,
        duplicate: false,
        retryable: false,
      };
    });
    setItems((current) => [...current, ...added]);
  }, []);

  const retry = useCallback(
    (id: number) => {
      setItems((current) =>
        current.map((item) =>
          item.id === id && item.status === "failed" && item.retryable
            ? { ...item, status: "queued", error: null, errorCode: null, progress: 0 }
            : item,
        ),
      );
    },
    [],
  );

  const remove = useCallback((id: number) => {
    controllers.current.get(id)?.abort();
    controllers.current.delete(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const clearFinished = useCallback(() => {
    setItems((current) => current.filter((item) => item.status !== "done"));
  }, []);

  return { items, add, retry, remove, clearFinished };
}
