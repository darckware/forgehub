import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { requestVersionCheck } from "@/lib/appVersion";
import App from "@/App";
import { ThemeProvider } from "@/lib/theme";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import "@/index.css";

const queryClient = new QueryClient({
  // MSG-052: a response that no longer fits a schema usually means this tab
  // predates a deploy -- check now instead of waiting for the next poll.
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof Error && error.name === "ZodError") requestVersionCheck();
    },
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
