import type { ClassValue } from "clsx";
import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Custom font-size utilities must not be merged as text colors.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      shadow: [
        "workspace-drawer",
        "workspace-dialog",
        "workspace-tab",
        "workspace-inspector",
        "workspace-toast",
      ],
      text: [
        "workspace-app-body",
        "workspace-button",
        "workspace-button-small",
        "workspace-badge",
        "workspace-overline",
        "workspace-caption",
        "workspace-label",
        "workspace-body",
        "workspace-section",
        "workspace-editor-compact",
        "workspace-subheading",
        "workspace-editor",
        "workspace-title-mobile",
        "workspace-title",
        "workspace-micro",
        "workspace-hint",
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
