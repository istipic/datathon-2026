# Blizu source probes — 2026-11-03

- zg-vrtici: CKAN geoportal-djecji-vrtici, resource 75200bbf-... CSV (ArcGIS export, spatialRefId=4326). 323 rows; X=lon 15.8x-16.1x, Y=lat 45.7x-45.9x → EPSG:4326 confirmed. Resource last_modified 2022-06-23. License cc-by.
- zg-vrtici-mjesta: CKAN slobodna-mjesta-u-vrticima-... has TWO CSVs (nannies "dadilje" and "gradski DV"), both snapshot 01.01.2025
  (resource name "Slobodna mjesta u gradskim DV - 01.01.2025..csv", last_modified 2025-01-02T11:43:38). newest_resource(CSV)
  picks the DV file (latest last_modified). Format: ';' separated, UTF-8 BOM, 3 header rows, names like "DV Budućnost".
- zg-skole: CKAN djeji-vrtii-osnovne-i-srednje-kole-grada-zagreba-inspire = INSPIRE WFS (transformiraj.nipp.hr), GetCapabilities
  saved. One feature type us-govserv:GovernmentalService; GetFeature OUTPUTFORMAT=application/geo+json SRSNAME=urn:ogc:def:crs:EPSG::4326
  → 603 Point features: earlyChildhoodEducation 331, primaryEducation 177, upperSecondaryEducation 95. NO names/addresses in the source
  (only inspireId.localId, serviceType). No license in CKAN metadata. Fallback to OSM schools NOT needed.
- zet-gtfs: https://zet.hr/gtfs-scheduled/latest → zip 18 807 798 B, Last-Modified 2026-10-21, feed_version 000397, feed_start 2026-10-21.
  calendar.txt has all weekday flags 0 → service days only via calendar_dates.txt (exception_type 1), covering 2026-10-21..2026-12-31.
