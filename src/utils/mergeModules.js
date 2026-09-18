import { knownFeatures } from '../data/knownFeatures';

export function withNotStarted(modules) {
  const present = new Set(modules.map(m => m.name));
  const missing = knownFeatures
    .filter(name => !present.has(name))
    .map((name, index) => ({
      id: `not-started-${index}`,
      name,
      color: 'gray',
      pct: 0,
      status: 'Not Started',
      failing: 0,
      details: [],
    }));

  return [...modules, ...missing];
}