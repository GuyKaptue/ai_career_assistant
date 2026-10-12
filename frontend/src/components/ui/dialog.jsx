import React, { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';

import { cn } from '../../lib/utils';
import { useI18n } from '../../i18n';
import { XIcon } from '../icons';

/** Elements that can receive focus, for the focus trap's Tab cycling. */
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const CLOSE_MS = 150;

/** Panel width presets. The overlay's padding keeps a gutter on phones. */
const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-2xl',
  '2xl': 'max-w-3xl',
};

/**
 * Open dialogs, top-most last. Only the top-most one reacts to Escape, so a
 * dialog opened on top of another (e.g. sign-in from Settings) closes alone.
 */
const openStack = [];

const DialogContext = createContext({
  onOpenChange: undefined,
  titleId: undefined,
  descriptionId: undefined,
});

/**
 * Shared modal — one design for every dialog in the app.
 *
 * Structure (a rounded card with three zones):
 *
 *   <Dialog open onOpenChange size>
 *     <DialogHeader>   title (+ description) and the close (X) button
 *     <DialogContent>  scrollable body: forms, settings sections …
 *     <DialogFooter>   action buttons
 *   </Dialog>
 *
 * Behaviour
 *   - always centred on screen, on every breakpoint (phones keep a gutter)
 *   - closes on overlay click, on the X button and on Escape
 *   - `role="dialog"` + `aria-modal`, labelled/described by DialogTitle /
 *     DialogDescription, focus moves in on open, is trapped while open and is
 *     restored to the opener on close; background scroll is locked
 *   - fade + scale on entry and exit (the card stays mounted for the exit)
 */
const Dialog = ({ open, onOpenChange, children, className, size = 'md', ...props }) => {
  const [mounted, setMounted] = useState(false);
  const [closing, setClosing] = useState(false);
  const panelRef = useRef(null);
  const restoreFocusRef = useRef(null);
  const pressStartedInsideRef = useRef(false);
  const stackToken = useRef({});
  const titleId = useId();
  const descriptionId = useId();

  // Mount/unmount, keeping the card mounted through the exit animation.
  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement;
      setMounted(true);
      setClosing(false);
      return undefined;
    }
    if (!mounted) {
      return undefined;
    }
    setClosing(true);
    const timer = window.setTimeout(() => {
      setMounted(false);
      setClosing(false);
      // Restore focus only once the card has actually gone, so focus is not
      // pulled off the animating-out dialog.
      const opener = restoreFocusRef.current;
      restoreFocusRef.current = null;
      if (opener && typeof opener.focus === 'function' && document.contains(opener)) {
        opener.focus({ preventScroll: true });
      }
    }, CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [open, mounted]);

  // Track stacking order for Escape handling.
  useEffect(() => {
    if (!open) return undefined;
    const token = stackToken.current;
    openStack.push(token);
    return () => {
      const index = openStack.indexOf(token);
      if (index !== -1) openStack.splice(index, 1);
    };
  }, [open]);

  // Escape closes the top-most open dialog.
  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(event) {
      if (event.key !== 'Escape') return;
      if (openStack[openStack.length - 1] !== stackToken.current) return;
      event.stopPropagation();
      onOpenChange?.(false);
    }
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open, onOpenChange]);

  // Lock background scroll.
  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  // Move focus into the card once it is mounted.
  useEffect(() => {
    if (!open || !mounted || !panelRef.current) return undefined;
    const panel = panelRef.current;
    const timer = window.setTimeout(() => {
      const first = panel.querySelector('[data-autofocus="true"]') || panel.querySelector(FOCUSABLE);
      (first || panel).focus({ preventScroll: true });
    }, 20);
    return () => window.clearTimeout(timer);
  }, [open, mounted]);

  // Focus trap: keep Tab inside the card.
  const handleKeyDown = useCallback((event) => {
    if (event.key !== 'Tab' || !panelRef.current) return;
    const focusable = Array.from(panelRef.current.querySelectorAll(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    );
    if (focusable.length === 0) {
      event.preventDefault();
      panelRef.current.focus({ preventScroll: true });
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    }
  }, []);

  if (!open && !mounted) return null;

  /**
   * The overlay *is* the dimmed backdrop, so a click that lands outside the
   * card reaches it directly. A press that started inside the card (e.g.
   * selecting text in an input and releasing outside) must not close it.
   */
  function handleOverlayMouseDown(event) {
    pressStartedInsideRef.current = event.target !== event.currentTarget;
  }

  function handleOverlayClick(event) {
    const startedInside = pressStartedInsideRef.current;
    pressStartedInsideRef.current = false;
    if (event.target === event.currentTarget && !startedInside) {
      onOpenChange?.(false);
    }
  }

  return (
    <DialogContext.Provider value={{ onOpenChange, titleId, descriptionId }}>
      <div
        className={cn(
          'fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-black/45 p-4 backdrop-blur-[2px] sm:p-6',
          closing ? 'aca-overlay-out' : 'aca-overlay-in',
        )}
        onMouseDown={handleOverlayMouseDown}
        onClick={handleOverlayClick}
      >
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          {...props}
          className={cn(
            'relative flex max-h-full w-full flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-strong outline-none',
            SIZES[size] || SIZES.md,
            closing ? 'aca-panel-out' : 'aca-panel-in',
            className,
          )}
        >
          {children}
        </div>
      </div>
    </DialogContext.Provider>
  );
};

const DialogTrigger = ({ children, ...props }) => React.cloneElement(children, props);

/** HEADER zone: title / description on the left, close (X) on the right. */
const DialogHeader = ({ className, children, hideClose = false, ...props }) => {
  const { onOpenChange } = useContext(DialogContext);
  const { t } = useI18n();
  const closeLabel = t('common.close', 'Close');

  return (
    <div
      className={cn('flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-6', className)}
      {...props}
    >
      <div className="min-w-0 flex-1 space-y-1">{children}</div>
      {!hideClose && (
        <button
          type="button"
          onClick={() => onOpenChange?.(false)}
          aria-label={closeLabel}
          title={closeLabel}
          className="-mr-2 -mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <XIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};
DialogHeader.displayName = 'DialogHeader';

const DialogTitle = React.forwardRef(({ className, id, ...props }, ref) => {
  const { titleId } = useContext(DialogContext);
  return (
    <h2
      ref={ref}
      id={id ?? titleId}
      className={cn('text-lg font-semibold leading-snug tracking-tight', className)}
      {...props}
    />
  );
});
DialogTitle.displayName = 'DialogTitle';

const DialogDescription = React.forwardRef(({ className, id, ...props }, ref) => {
  const { descriptionId } = useContext(DialogContext);
  return <p ref={ref} id={id ?? descriptionId} className={cn('text-sm text-muted-foreground', className)} {...props} />;
});
DialogDescription.displayName = 'DialogDescription';

/** CONTENT zone: the scrollable body, so a short viewport never clips the footer. */
const DialogContent = React.forwardRef(({ className, children, onClose, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6', className)}
    {...props}
  >
    {children}
  </div>
));
DialogContent.displayName = 'DialogContent';

/** FOOTER zone: action buttons, always visible below the scrolling content. */
const DialogFooter = ({ className, ...props }) => (
  <div
    className={cn(
      'flex shrink-0 flex-col-reverse gap-2 border-t border-border bg-card px-5 py-4 sm:flex-row sm:items-center sm:justify-end sm:px-6',
      className,
    )}
    {...props}
  />
);
DialogFooter.displayName = 'DialogFooter';

export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
};
