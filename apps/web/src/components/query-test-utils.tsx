import {
  render as rtlRender,
  type RenderOptions,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";
export * from "@testing-library/react";
export function render(ui: ReactElement, options?: RenderOptions) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 30_000, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const Wrapper = options?.wrapper;
  return {
    ...rtlRender(ui, {
      ...options,
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>
          {Wrapper ? <Wrapper>{children}</Wrapper> : children}
        </QueryClientProvider>
      ),
    }),
    queryClient: client,
  };
}
