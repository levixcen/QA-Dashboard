import { knownFeatures } from '../data/knownFeatures';

export function withNotStarted(modules, extraFeatureNames = []) {
  const present = new Set(modules.map(m => m.name));
  const allKnown = [...new Set([...knownFeatures, ...extraFeatureNames])];
  const missing = allKnown
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