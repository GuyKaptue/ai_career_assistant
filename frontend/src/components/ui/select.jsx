import React from 'react';
import { cn } from '../../lib/utils';

const FIELD =
  'flex h-10 w-full items-center justify-between rounded-lg border border-input bg-card px-3 py-2 text-sm text-foreground ' +
  'transition-[border-color,box-shadow] focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/25 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

const Select = React.forwardRef(({ className, ...props }, ref) => (
  <select ref={ref} className={cn(FIELD, className)} {...props} />
));
Select.displayName = 'Select';

const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(FIELD, className)}
    {...props}
  >
    {children}
  </div>
));
SelectTrigger.displayName = 'SelectTrigger';

const SelectValue = React.forwardRef(({ className, placeholder, ...props }, ref) => (
  <span
    ref={ref}
    className={cn('text-sm', className)}
    {...props}
  >
    {placeholder && <span className="text-muted-foreground">{placeholder}</span>}
  </span>
));
SelectValue.displayName = 'SelectValue';

const SelectContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'relative z-50 min-w-[8rem] overflow-y-auto overflow-x-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-medium',
      className
    )}
    {...props}
  >
    <div className="p-1">{children}</div>
  </div>
));
SelectContent.displayName = 'SelectContent';

const SelectItem = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'relative flex w-full cursor-default select-none items-center rounded-md py-1.5 pl-2 pr-8 text-sm outline-none',
      'data-[highlighted=true]:bg-accent data-[highlighted=true]:text-accent-foreground',
      'data-[selected=true]:bg-primary data-[selected=true]:text-primary-foreground',
      className
    )}
    {...props}
  >
    <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
      <svg className="h-4 w-4 opacity-0 transition-opacity group-data-[selected=true]:opacity-100" viewBox="0 0 14 14">
        <path
          fill="currentColor"
          d="M12.25 2.0995l-7.5 7.5-2.25 2.25-1.5-1.5 3-3-3-3 1.5-1.5 2.25 2.25 7.5-7.5 1.0607 1.0607z"
        />
      </svg>
    </span>
    {children}
  </div>
));
SelectItem.displayName = 'SelectItem';

const SelectSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('-mx-1 my-1 h-px bg-muted', className)}
    {...props}
  />
));
SelectSeparator.displayName = 'SelectSeparator';

export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  SelectSeparator,
};
