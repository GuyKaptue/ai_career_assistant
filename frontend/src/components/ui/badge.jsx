import React from 'react';
import { cn } from '../../lib/utils';

const badgeVariants = {
  variant: {
    default: 'bg-primary text-primary-foreground',
    secondary: 'bg-secondary text-secondary-foreground',
    destructive: 'bg-destructive text-destructive-foreground',
    outline: 'border border-border-strong bg-transparent text-foreground',
  },
  size: {
    default: 'px-2.5 py-0.5 text-xs',
    sm: 'px-2 py-0.5 text-xs',
    lg: 'px-3 py-1 text-sm',
  },
};

const Badge = React.forwardRef(({ className, variant = 'default', size = 'default', ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'inline-flex items-center rounded-full font-medium',
      badgeVariants.variant[variant],
      badgeVariants.size[size],
      className,
    )}
    {...props}
  />
));
Badge.displayName = 'Badge';

export { Badge, badgeVariants };
