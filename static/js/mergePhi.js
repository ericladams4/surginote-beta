export function mergePHI(template, phi) {
  return String(template || "").replace(/\{\{(\w+)\}\}/g, (_, key) => String((phi && phi[key]) || `[${key}_MISSING]`));
}
