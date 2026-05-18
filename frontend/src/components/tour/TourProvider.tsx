import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { TOUR_STEPS } from "@/components/tour/steps";
import { TourSpotlight } from "@/components/tour/TourSpotlight";
import { TourTooltip } from "@/components/tour/TourTooltip";

const STORAGE_KEY = "sift.tour.v2";
const AUTOSTART_DELAY_MS = 600;

type TourCtx = {
  isActive: boolean;
  currentStep: number;
  totalSteps: number;
  start: () => void;
  next: () => void;
  back: () => void;
  skip: () => void;
};

const Ctx = createContext<TourCtx | null>(null);

export function useTour(): TourCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTour must be used inside <TourProvider>");
  return ctx;
}

function isInbox(pathname: string): boolean {
  return pathname === "/" || pathname === "/inbox";
}

export function TourProvider({ children }: { children: ReactNode }) {
  const [isActive, setIsActive] = useState(false);
  const [step, setStep] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  const total = TOUR_STEPS.length;

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(STORAGE_KEY)) return;
    if (!isInbox(location.pathname)) return;
    const t = window.setTimeout(() => setIsActive(true), AUTOSTART_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [location.pathname]);

  const persistDone = useCallback(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, "1");
    }
  }, []);

  const start = useCallback(() => {
    setStep(0);
    setIsActive(true);
    const first = TOUR_STEPS[0];
    if (first?.route && location.pathname !== first.route) {
      navigate(first.route);
    }
  }, [navigate, location.pathname]);

  const next = useCallback(() => {
    setStep((s) => {
      const n = s + 1;
      if (n >= total) {
        setIsActive(false);
        persistDone();
        return 0;
      }
      const nextStep = TOUR_STEPS[n];
      if (nextStep?.route && location.pathname !== nextStep.route) {
        navigate(nextStep.route);
      }
      return n;
    });
  }, [navigate, location.pathname, total, persistDone]);

  const back = useCallback(() => {
    setStep((s) => Math.max(0, s - 1));
  }, []);

  const skip = useCallback(() => {
    setIsActive(false);
    setStep(0);
    persistDone();
  }, [persistDone]);

  useEffect(() => {
    if (!isActive) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const editable =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (editable) return;
      if (e.key === "Escape") {
        e.preventDefault();
        skip();
      } else if (e.key === "ArrowRight" || e.key === "Enter") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        back();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [isActive, next, back, skip]);

  const value = useMemo<TourCtx>(
    () => ({
      isActive,
      currentStep: step,
      totalSteps: total,
      start,
      next,
      back,
      skip,
    }),
    [isActive, step, total, start, next, back, skip],
  );

  const current = TOUR_STEPS[step];

  return (
    <Ctx.Provider value={value}>
      {children}
      {isActive && current && (
        <>
          <TourSpotlight selector={current.selector} />
          <TourTooltip step={current} index={step} total={total} />
        </>
      )}
    </Ctx.Provider>
  );
}
