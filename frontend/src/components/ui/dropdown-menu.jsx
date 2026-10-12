import React, { createContext, useContext } from 'react';

import { cn } from '../../lib/utils';

/**
 * Dropdown menu primitives.
 *
 * The open/closed state lives on `DropdownMenu` and is shared with the trigger
 * and the content through context (an earlier version kept separate state in
 * each, so the menu never opened).
 *
 * Keyboard: the first item is focused on open, ArrowUp/ArrowDown/Home/End move
 * between items, Enter/Space select, Escape closes and returns focus to the
 * trigger. Clicking outside closes it.
 */

const DropdownMenuContext = createContext({
  open: false,
  setOpen: () => {},
  triggerRef: { current: null },
});

const DropdownMenu = ({ children, className, ...props }) => {
  const [open, setOpen] = React.useState(false);
  const triggerRef = React.useRef(null);

  return (
    <DropdownMenuContext.Provider value={{ open, setOpen, triggerRef }}>
      <div className={cn('relative inline-block', className)} {...props}>
        {children}
      </div>
    </DropdownMenuContext.Provider>
  );
};

const DropdownMenuTrigger = React.forwardRef(
  ({ className, children, asChild, onClick, ...props }, ref) => {
    const { open, setOpen, triggerRef } = useContext(DropdownMenuContext);

    const setRefs = (node) => {
      triggerRef.current = node;
      if (typeof ref === 'function') ref(node);
      else if (ref) ref.current = node;
    };

    const handleClick = (event) => {
      event.stopPropagation();
      setOpen(!open);
      onClick?.(event);
    };

    if (asChild) {
      return React.cloneElement(children, {
        ref: setRefs,
        onClick: handleClick,
        className: cn(className, children.props.className),
        'aria-expanded': open,
        'aria-haspopup': 'menu',
        ...props,
      });
    }

    return (
      <button
        ref={setRefs}
        type="button"
        onClick={handleClick}
        className={cn(
          'flex items-center justify-between rounded-lg border border-input bg-card px-3 py-2 text-sm font-medium',
          className,
        )}
        aria-expanded={open}
        aria-haspopup="menu"
        {...props}
      >
        {children}
      </button>
    );
  },
);
DropdownMenuTrigger.displayName = 'DropdownMenuTrigger';

const DropdownMenuContent = React.forwardRef(
  ({ className, children, align = 'start', side = 'bottom', ...props }, ref) => {
    const { open, setOpen, triggerRef } = useContext(DropdownMenuContext);
    const [panel, setPanel] = React.useState(null);

    React.useEffect(() => {
      if (!open) return undefined;

      function handleClickOutside(event) {
        const root = panel?.parentElement;
        if (root && !root.contains(event.target)) {
          setOpen(false);
        }
      }

      function handleKeyDown(event) {
        if (event.key === 'Escape') {
          setOpen(false);
          triggerRef.current?.focus?.({ preventScroll: true });
        }
      }

      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        document.removeEventListener('keydown', handleKeyDown);
      };
    }, [open, panel, setOpen, triggerRef]);

    // Focus the first item when the menu opens.
    React.useEffect(() => {
      if (open && panel) {
        panel.querySelector('[role="menuitem"]')?.focus({ preventScroll: true });
      }
    }, [open, panel]);

    if (!open) return null;

    function handlePanelKeyDown(event) {
      const items = Array.from(panel?.querySelectorAll('[role="menuitem"]') || []);
      if (items.length === 0) return;
      const index = items.indexOf(document.activeElement);
      let next = null;
      if (event.key === 'ArrowDown') next = items[(index + 1) % items.length];
      else if (event.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length];
      else if (event.key === 'Home') next = items[0];
      else if (event.key === 'End') next = items[items.length - 1];
      if (next) {
        event.preventDefault();
        next.focus({ preventScroll: true });
      }
    }

    return (
      <div
        ref={(node) => {
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
          setPanel(node);
        }}
        className={cn(
          'aca-menu-in absolute z-50 min-w-[8rem] rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-medium',
          side === 'top' ? 'bottom-full mb-2' : 'top-full mt-2',
          align === 'end' && 'right-0',
          align === 'start' && 'left-0',
          align === 'stretch' && 'inset-x-0',
          className,
        )}
        role="menu"
        onKeyDown={handlePanelKeyDown}
        {...props}
      >
        {children}
      </div>
    );
  },
);
DropdownMenuContent.displayName = 'DropdownMenuContent';

const DropdownMenuItem = React.forwardRef(
  ({ className, onSelect, children, ...props }, ref) => {
    const { setOpen, triggerRef } = useContext(DropdownMenuContext);

    function select(event) {
      event.stopPropagation();
      onSelect?.();
      // Selecting an item dismisses the menu.
      setOpen(false);
    }

    function handleKeyDown(event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        select(event);
        triggerRef.current?.focus?.({ preventScroll: true });
      }
    }

    return (
      <div
        ref={ref}
        onClick={select}
        onKeyDown={handleKeyDown}
        role="menuitem"
        tabIndex={-1}
        className={cn(
          'relative flex cursor-pointer select-none items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm outline-none',
          'hover:bg-accent focus-visible:bg-accent focus:bg-accent',
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
DropdownMenuItem.displayName = 'DropdownMenuItem';

const DropdownMenuSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} role="separator" className={cn('-mx-1.5 my-1.5 h-px bg-border', className)} {...props} />
));
DropdownMenuSeparator.displayName = 'DropdownMenuSeparator';

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
};
