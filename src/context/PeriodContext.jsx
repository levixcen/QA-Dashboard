import { createContext, useContext, useState, useCallback } from 'react';

const STORAGE_KEY = 'selectedPeriod';
const PeriodContext = createContext({ period: null, setPeriod: () => {} });

function readStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return /^\d{4}-(0[1-9]|1[0-2])$/.test(v || '') ? v : null;
  } catch {
    return null;
  }
}

export function PeriodProvider({ children }) {
  const [period, setPeriodState] = useState(readStored);

  const setPeriod = useCallback(value => {
    setPeriodState(value);
    try {
      if (value) localStorage.setItem(STORAGE_KEY, value);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  return (
    <PeriodContext.Provider value={{ period, setPeriod }}>
      {children}
    </PeriodContext.Provider>
  );
}

export function usePeriod() {
  return useContext(PeriodContext);
}