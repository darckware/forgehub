import React from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

/** Top-level safety net -- without this, any uncaught render-time error
 * anywhere in the tree unmounts the whole app, leaving nothing but the
 * <div id="root">'s background color (a blank screen indistinguishable
 * from "still loading"), recoverable only by the user guessing to hit
 * reload. This turns that into a visible, actionable error with a reload
 * button instead. */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen w-full flex-col items-center justify-center gap-4 bg-background p-8 text-center">
          <AlertTriangle className="h-10 w-10 text-destructive" />
          <div className="space-y-1">
            <h1 className="text-lg font-semibold">Something went wrong</h1>
            <p className="max-w-md text-sm text-muted-foreground">
              {this.state.error.message || "An unexpected error occurred while rendering the page."}
            </p>
          </div>
          <Button onClick={() => window.location.reload()} className="gap-2">
            <RotateCw className="h-4 w-4" />
            Reload
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
