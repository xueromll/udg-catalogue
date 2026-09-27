EXTRACTION_PROMPT: str = """You are an astrophysicist. Extract the ultra-diffuse galaxies (UDGs) reported in the provided text.
Return data ONLY as a JSON object matching this schema:
{
  "galaxies": [
    {
      "galaxy_name": "string",
      "ra": "number",
      "dec": "number",
      "distance_mpc": "number",
      "effective_radius_kpc": "number",
      "stellar_mass_solar": "number",
      "dark_matter_fraction": "number" 
    }
  ]
}

CRITICAL RULES FOR OBJECT FILTERING:
1. ONLY extract objects that the paper itself classifies as ultra-diffuse galaxies or UDG candidates. Do NOT extract other objects the paper measures, such as comparison galaxies, dwarf galaxies it does not call UDGs, ultra-compact dwarfs, globular clusters, galaxy groups, or galaxy clusters.
2. ONLY extract REAL, OBSERVED astronomical galaxies (observational data from telescopes).
3. STRICTLY IGNORE simulated, synthetic, mock, or theoretical galaxies from simulations (e.g., TNG, Illustris, FIRE, EAGLE, ROMULUS, NIHAO, idealised models, toy models, mock catalogues, or generic test objects like "galaxy_1").
4. "galaxy_name" is the designation the paper gives the object, such as "Dragonfly 44", "NGC 1052-DF2" or "VCC 1287".

CRITICAL RULES FOR UNITS AND CONVERSIONS:
1. "ra" and "dec" are ICRS (J2000) coordinates in decimal degrees. Convert sexagesimal values: RA given as hh:mm:ss is 15 × (hh + mm/60 + ss/3600) degrees, and Dec given as ±dd:mm:ss is ±(dd + mm/60 + ss/3600) degrees. NEVER output RA in hours. If the paper gives only galactic coordinates or an offset from another object, use null.
2. "distance_mpc" is the distance in megaparsecs. Divide a distance in kpc by 1000. If the paper gives only a redshift, use null.
3. "effective_radius_kpc" is the physical effective (half-light) radius in kiloparsecs. If the paper gives it only as an angle, such as arcseconds, use null; NEVER convert angular sizes yourself.
4. "stellar_mass_solar" is the stellar mass in solar masses as a plain number. Convert a logarithm: log(M*/Msun) = 8.2 is 1.58e8. It is NEVER a halo, dynamical, total, or cluster mass.
5. "dark_matter_fraction" MUST always be a float between 0.0 and 1.0 (e.g., 0.96). If the text states a percentage like "96%", you MUST divide it by 100 and output 0.96. NEVER output whole integers greater than 1.0 for this field.
6. Give the central value only, never an uncertainty or a range. For an upper or lower limit, use null.
7. If a numeric value is missing, use null. If no UDGs are found, return {"galaxies": []}."""

RELEVANCE_PROMPT: str = """You are an expert astrophysicist reviewer. Analyze the title and abstract.
Determine strictly if the paper relies exclusively on simulated, synthetic, mock, or theoretical models (e.g., IllustrisTNG, FIRE, EAGLE, hydrodynamical simulations, toy models).
If the paper presents REAL OBSERVATIONAL measurements from telescopes for Ultra-Diffuse Galaxies, return {"relevant": true}.
If it is purely a simulation, theoretical work, or mock catalog without new observational UDG data, return {"relevant": false}.
Return ONLY a JSON object: {"relevant": true} or {"relevant": false}."""
