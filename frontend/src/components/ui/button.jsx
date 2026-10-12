import React from 'react';
import { cn } from '../../lib/utils';

/**
 * Claude-style buttons: clay primary, quiet bordered secondary, ghost for
 * toolbars. Focus is drawn by the global :focus-visible rule (styles.css), so
 * no per-component ring is needed.
 */
const buttonVariants = {
  variant: {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.985]',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
    outline: 'border border-border-strong bg-transparent text-foreground hover:bg-accent',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-accent',
    ghost: 'text-foreground hover:bg-accent',
    link: 'text-primary underline-offset-4 hover:underline',
  },
  size: {
    default: 'h-9 px-4 py-2',
    sm: 'h-8 px-3',
    lg: 'h-10 px-5',
    icon: 'h-9 w-9 p-0',
  },
};

const Button = React.forwardRef(({ className, variant = 'default', size = 'default', type = 'button', ...props }, ref) => {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-[background-color,color,transform] duration-150',
        'disabled:pointer-events-none disabled:opacity-50',
        buttonVariants.variant[variant],
        buttonVariants.size[size],
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Button.displayName = 'Button';

export { Button, buttonVariants };
