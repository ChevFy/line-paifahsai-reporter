import { useCallback, useEffect, useState } from "react";
import { getMyVolunteer } from "../services/volunteer-service";
import type { VolunteerRegistrationResponse } from "../types/volunteer";
import { toDisplayError } from "../utils/app-error";
import type { DisplayError } from "../utils/app-error";

export type MyVolunteerState =
  | { kind: "loading" }
  | { kind: "not-registered" }
  | { kind: "registered"; registration: VolunteerRegistrationResponse }
  | { kind: "error"; error: DisplayError };

async function fetchMyVolunteerState(): Promise<MyVolunteerState> {
  try {
    const registration = await getMyVolunteer();
    return registration ? { kind: "registered", registration } : { kind: "not-registered" };
  } catch (reason) {
    return { kind: "error", error: toDisplayError(reason, "loadVolunteer") };
  }
}

export function useMyVolunteer() {
  const [state, setState] = useState<MyVolunteerState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    void fetchMyVolunteerState().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(async () => {
    setState({ kind: "loading" });
    setState(await fetchMyVolunteerState());
  }, []);

  const setRegistration = useCallback((registration: VolunteerRegistrationResponse) => {
    setState({ kind: "registered", registration });
  }, []);

  return { state, reload, setRegistration };
}
