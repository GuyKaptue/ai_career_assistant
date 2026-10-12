import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Tailwind merge instance aware of the design-system shadow scale.
 *
 * The project defines custom shadow tokens in `@theme`
 * (`--shadow-soft`, `--shadow-medium`, `--shadow-strong`,
 * `--shadow-recessed`) which produce the utilities `shadow-soft`,
 * `shadow-medium`, `shadow-strong` and `shadow-inset`. tailwind-merge does
 * not know these tokens, so without this config a component that receives
 * both a variant shadow (e.g. `shadow-xs`) and an override (`shadow-soft`)
 * ends up with BOTH classes on the element, and the winner is then decided
 * by CSS source order instead of by the order the classes were passed. That
 * silently swallowed the shadows on the suggested-prompt cards.
 *
 * Adding the custom values into the `shadow` class group means the last one
 * passed always wins, matching normal Tailwind behaviour.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      shadow: [{ shadow: ["soft", "medium", "strong", "recessed", "inset"] }],
    },
  },
});

/**
 * Utility function to merge Tailwind CSS classes
 * Combines clsx for conditional classes with tailwind-merge for deduplication
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
