function yamlScalar(value) {
  if (value === null) return "null";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "string") return JSON.stringify(value);
  return JSON.stringify(value);
}

function serialize(value, indent) {
  const pad = " ".repeat(indent);
  if (Array.isArray(value)) {
    if (!value.length) return `${pad}[]`;
    return value.map((item) => {
      if (!item || typeof item !== "object") return `${pad}- ${yamlScalar(item)}`;
      const entries = Object.entries(item);
      const [first, ...rest] = entries;
      const firstLine = first[1] && typeof first[1] === "object"
        ? `${pad}- ${first[0]}:\n${serialize(first[1], indent + 4)}`
        : `${pad}- ${first[0]}: ${yamlScalar(first[1])}`;
      const remaining = rest.map(([key, nested]) => nested && typeof nested === "object"
        ? `${pad}  ${key}:\n${serialize(nested, indent + 4)}`
        : `${pad}  ${key}: ${yamlScalar(nested)}`);
      return [firstLine, ...remaining].join("\n");
    }).join("\n");
  }
  if (value && typeof value === "object") return Object.entries(value).map(([key, nested]) => nested && typeof nested === "object"
    ? `${pad}${key}:\n${serialize(nested, indent + 2)}`
    : `${pad}${key}: ${yamlScalar(nested)}`).join("\n");
  return `${pad}${yamlScalar(value)}`;
}

export function toYaml(value) {
  return `${serialize(value, 0)}\n`;
}
