from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from custom_code.models import VariableStar
from custom_code import variable_stars
import numpy as np
from collections import Counter
from os import path
from astropy.coordinates import SkyCoord, search_around_sky
from astropy import units as u
import logging

logger = logging.getLogger(__name__)

# Stars closer together than this are taken to be the same star
MATCH_RADIUS = 0.5 * u.arcsec

# The type of a star that is known to be variable but hasn't been classified
UNCLASSIFIED_TYPE = 'OGLE variable'

# The variable types named in the headers of the typed OGLE catalogs, which are the types the stars are
# given. A star in more than one typed catalog has all of its types, joined (see variable_stars.combine).
# Headers are compared without regard to case.
OGLE_TYPES = [
    'Cepheid', 'Delta Scuti', 'Eclipsing binary', 'Long Period Variable', 'OGLE Variable', 'RR Lyra',
    'Spotted star',
]

# Misspellings in the headers
OGLE_TYPE_ALIASES = {'cephied': 'Cepheid'}

class Command(BaseCommand):
    help = 'Tool to ingest a catalog of variable stars, skipping any that RogueDB already knows'

    def add_arguments(self, parser):
        parser.add_argument('catalog_path', help='Path to the ASCII catalog file')
        parser.add_argument('format', help='Catalog format {MOA, OGLE, OGLE_TYPED}')

    def handle(self, *args, **options):

        # Load the variable star catalog, parsing the entries so as to
        # produce the parameter set expected by the database model
        catalog_format = str(options['format']).upper()
        if catalog_format == 'MOA':
            use_id = 'moa_id'   # ID in the table to identify with
            catalog_entries = self.parse_moa_catalog(options)
        elif catalog_format == 'OGLE':
            use_id = 'ogle_id'
            catalog_entries = self.parse_ogle_catalog(options)
        elif catalog_format == 'OGLE_TYPED':
            use_id = 'ogle_id'
            catalog_entries = self.parse_ogle_typed_catalog(options)
        else:
            raise CommandError('Unknown catalog format ' + options['format'] + ', expected MOA, OGLE or OGLE_TYPED')
        logger.info('Read ' + str(len(catalog_entries)) + ' entries from catalog')

        # Only the typed catalogs say what type their stars are
        update_types = (catalog_format == 'OGLE_TYPED')

        # Review the new catalog entries, comparing them with those in the database
        # to avoid duplication
        new_variables, matched = self.find_new_variables(catalog_entries, use_id)

        # Some stars have already been ingested from other catalogs. Where the catalog's entry matches
        # one of them, record the catalog's name for it, unless it already has a name from this
        # catalog, which we don't want to overwrite. A typed catalog also updates the star's type.
        stars = {}
        pks = list({pk for entry, pk in matched})
        for start in range(0, len(pks), 5000):
            stars.update(VariableStar.objects.in_bulk(pks[start:start + 5000]))
        changed = {}
        retyped = Counter()
        for entry, pk in matched:
            star = stars[pk]
            if not getattr(star, use_id):
                setattr(star, use_id, entry[use_id])
                changed[pk] = star
            if update_types:
                new_type = self.updated_type(star.type, entry['type'])
                if new_type != star.type:
                    retyped[(star.type, new_type)] += 1
                    star.type = new_type
                    changed[pk] = star

        # Ingest any new variables. This is all or nothing, so a failure doesn't leave the
        # catalog half ingested
        logger.info('Ingesting ' + str(len(new_variables)) + ' new variables, and updating '
                    + str(len(changed)) + ' known ones')
        for (old_type, new_type), count in retyped.most_common():
            logger.info('Type of ' + str(count) + ' known stars changed: ' + str(old_type) + ' -> ' + str(new_type))
        with transaction.atomic():
            VariableStar.objects.bulk_update(
                list(changed.values()), [use_id, 'type'] if update_types else [use_id], batch_size=1000
            )
            VariableStar.objects.bulk_create(
                [VariableStar(**vstar) for vstar in new_variables], batch_size=5000
            )

    def updated_type(self, current_type, catalog_type):
        """
        The type a known star should have, given the one it has and the one the catalog gives it.
        Where the star's type is already from the typed catalogs, because it is in another of them, it
        has both, joined and in alphabetical order (see variable_stars.combine), so it comes out the
        same whichever catalog was ingested first. A star that was in a typed catalog has any types
        it was given in other ways kept (such as when stars were merged: see merge_colocated_variables).
        Otherwise the type it has, from earlier ingests, is replaced.
        """
        if any(name in OGLE_TYPES for name in variable_stars.split(current_type)):
            return variable_stars.combine(current_type, catalog_type)
        return catalog_type

    def find_new_variables(self, catalog_entries, use_id):
        """
        Compare the entries of a catalog with the variable stars already in the database, with
        a cross-match of all of them at once

        Parameters:
            catalog_entries     list    Dictionaries of VariableStar parameters, including ra and dec in degrees
            use_id              str     The VariableStar ID field that the catalog provides

        Returns:
            new_variables       list    The entries that aren't in the database
            matched             list    (entry, pk) for each entry that is a known star, where pk is the
                                        primary key of the star with its name or, failing that, with its
                                        position (the closest one if more than one)
        """

        # A star the database already has under the same name is the same star. Names are only
        # compared within the catalog's own ID field.
        known_pks = variable_stars.known_variable_pks(use_id)
        matched = [(vstar, known_pks[vstar[use_id]]) for vstar in catalog_entries if vstar[use_id] in known_pks]
        entries = [vstar for vstar in catalog_entries if vstar[use_id] not in known_pks]
        logger.info(str(len(matched)) + ' entries are already known by name')

        # The rest are looked for by position
        if len(entries) == 0 or not VariableStar.objects.exists():
            return entries, matched
        existing_var_positions, existing_var_pks = variable_stars.known_variable_positions()
        positions = self.skycoords(entries)
        idx_entry, idx_known, sep, _ = search_around_sky(positions, existing_var_positions, MATCH_RADIUS)

        # More than one known star can be in range: take the closest. Sorting by entry and then by
        # separation puts it first among each entry's matches. The table has stars at exactly the same
        # position (the same star in two catalogs), which are equally close, and the earliest added of
        # them is taken, so that which one it is doesn't depend on the order the database returns
        # them in, and so doesn't change from one ingest to the next.
        order = np.lexsort((existing_var_pks[idx_known], sep.arcsec, idx_entry))
        idx_entry, idx_known = idx_entry[order], idx_known[order]
        first_match = np.unique(idx_entry, return_index=True)[1]
        matched_idx = {int(i): int(existing_var_pks[j]) for i, j in zip(idx_entry[first_match], idx_known[first_match])}
        new_variables = [vstar for i, vstar in enumerate(entries) if i not in matched_idx]
        logger.info(str(len(matched_idx)) + ' entries matched the position of a known star, '
                    + str(len(new_variables)) + ' are new')

        return new_variables, matched + [(entries[i], pk) for i, pk in matched_idx.items()]

    def skycoords(self, entries):
        """The positions of a list of entries, as one SkyCoord"""
        return SkyCoord(
            np.array([vstar['ra'] for vstar in entries]), np.array([vstar['dec'] for vstar in entries]),
            frame='icrs', unit=(u.deg, u.deg)
        )

    def remove_internal_duplicates(self, catalog_entries):
        """
        The catalog has to be scanned for duplicates within itself. Since stars can be detected
        multiple times in the same survey, name-matching is unreliable, so we use a position match.
        Each entry that has another within the match radius, earlier in the catalog, is dropped.
        """
        if len(catalog_entries) < 2:
            return catalog_entries

        positions = self.skycoords(catalog_entries)
        idx_a, idx_b, _, _ = search_around_sky(positions, positions, MATCH_RADIUS)
        duplicates = set(idx_b[idx_a < idx_b].tolist())

        return [vstar for i, vstar in enumerate(catalog_entries) if i not in duplicates]

    def parse_moa_catalog(self, options):
        """
        Method to parse variable star coordinates from a MOA-style catalog
        Expects ASCII format data with columns:
        Identifier  designation  RA(sexig)  Dec(sexig)  Comment
        """

        with open(options['catalog_path'], 'r') as f:
            lines = [line.split() for line in f.read().splitlines() if line.strip()]

        # The coordinates are sexigesimal strings, in hours for the RA
        s = SkyCoord([entries[2] for entries in lines], [entries[3] for entries in lines],
                     frame='icrs', unit=(u.hourangle, u.deg))

        catalog_entries = [
            {
                'moa_id': entries[0],
                'ra': ra, 'dec': dec,
                'ogle_id': None, 'vvv_id': None, 'gaia_id': None,
                'type': ' '.join(entries[4:])
            }
            for entries, ra, dec in zip(lines, s.ra.deg, s.dec.deg)
        ]

        return self.remove_internal_duplicates(catalog_entries)

    def parse_ogle_catalog(self, options):
        """
        Method to parse an OGLE field catalog of variable stars
        The columns used are the first three:
        Identifier  RA (degrees)  Dec (degrees)
        These files contain no variable type information
        """

        if not path.isfile(options['catalog_path']):
            raise CommandError('Cannot find input catalog ' + options['catalog_path'])

        with open(options['catalog_path'], 'r') as f:
            lines = [line.split() for line in f.read().splitlines() if line.strip()]

        catalog_entries = [
            {
                'ogle_id': entries[0],
                'ra': float(entries[1]), 'dec': float(entries[2]),
                'moa_id': None, 'vvv_id': None, 'gaia_id': None,
                'type': UNCLASSIFIED_TYPE
            }
            for entries in lines
        ]

        return self.remove_internal_duplicates(catalog_entries)

    def parse_ogle_typed_catalog(self, options):
        """
        Method to parse an OGLE catalog of variable stars which has been split into
        separate files depending on the type of variable
        These files have three columns:
        Identifier  RA (degrees)  Dec (degrees)
        These files contain the variable type as a commented header line, on the first line
        """

        if not path.isfile(options['catalog_path']):
            raise CommandError('Cannot find input catalog ' + options['catalog_path'])

        with open(options['catalog_path'], 'r') as f:
            header, *body = f.read().splitlines()
        lines = [line.split() for line in body if line.strip()]

        # The header names the type
        catalog_type = header.lstrip('#').strip()
        catalog_type = OGLE_TYPE_ALIASES.get(catalog_type.lower(), catalog_type)
        known_types = {name.lower(): name for name in OGLE_TYPES}
        if not header.startswith('#') or catalog_type.lower() not in known_types:
            raise CommandError('The first line of ' + options['catalog_path'] + ' should be a header naming '
                               'one of the types in OGLE_TYPES, but is "' + header + '"')
        catalog_type = known_types[catalog_type.lower()]

        catalog_entries = [
            {
                'ogle_id': entries[0],
                'ra': float(entries[1]), 'dec': float(entries[2]),
                'moa_id': None, 'vvv_id': None, 'gaia_id': None,
                'type': catalog_type
            }
            for entries in lines
        ]

        return self.remove_internal_duplicates(catalog_entries)
