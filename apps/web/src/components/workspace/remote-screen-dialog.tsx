"use client";

import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";

/** Native modal semantics keep focus and keyboard input inside the remote computer. */
export function RemoteScreenDialog({ children, connected, onClose, returnFocus }: { children: ReactNode; connected: boolean; onClose: () => void; returnFocus: RefObject<HTMLButtonElement | null> }) {
  const { t } = useLocale();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    const fallback = returnFocus.current;
    element?.showModal();
    return () => { element?.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); else fallback?.focus(); };
  }, [returnFocus]);
  return createPortal(<dialog ref={dialog} className="app-shell ag-app ag-remote-browser" aria-label={t("computer.remoteBrowser")} onCancel={(event) => { event.preventDefault(); onClose(); }} onKeyDown={(event) => { if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); onClose(); } }}>
    <header className="ag-remote-browser__head"><Icon name="panelRight" size={19} /><strong>{t("computer.remoteBrowser")}</strong><span className={`ag-remote-connection ${connected ? "is-connected" : ""}`} role="status">{t(connected ? "computer.live" : "computer.waitingForFrame")}</span><span className="ag-spacer" /><button type="button" className="ag-iconbtn" aria-label={t("common.close")} onClick={onClose}><Icon name="close" size={18} /></button></header>
    <div className="ag-remote-browser__body">{children}</div>
    <footer className="ag-remote-browser__foot"><span>{t("computer.remoteHint")}</span><kbd>Esc</kbd><span>{t("computer.closeOrHandBack")}</span></footer>
  </dialog>, document.body);
}
