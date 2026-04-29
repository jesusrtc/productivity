/** Extract IOCs (IPs, domains, hashes, member IDs) from text */
export function extractIOCs(text: string): string[] {
  const iocs = new Set<string>()
  // IPv4 addresses
  const ipv4 = text.match(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g)
  if (ipv4) ipv4.forEach(ip => iocs.add(ip))
  // Hex hashes (32+ chars)
  const hashes = text.match(/\b[a-f0-9]{32,}\b/gi)
  if (hashes) hashes.forEach(h => iocs.add(h))
  // Canvas hashes (0x prefix)
  const canvasHashes = text.match(/0x[a-f0-9]{6,}/gi)
  if (canvasHashes) canvasHashes.forEach(h => iocs.add(h))
  // Domains with suspicious TLDs
  const domains = text.match(/\b[a-z0-9][-a-z0-9]*\.(xyz|icu|top|us|ru|cn|tk|ml|ga|cf|gq|info|club|online|site|store)\b/gi)
  if (domains) domains.forEach(d => iocs.add(d.toLowerCase()))
  // Member IDs (7+ digit numbers, skip dates)
  const memberIds = text.match(/\b\d{7,12}\b/g)
  if (memberIds) memberIds.filter(id => !id.startsWith('202')).slice(0, 20).forEach(id => iocs.add(id))
  return [...iocs]
}
