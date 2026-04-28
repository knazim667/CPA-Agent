"""Bank Reconciliation Engine"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import csv

class ReconciliationEngine:
    def parse_bank_statement(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse bank statement from CSV or PDF."""
        if file_path.suffix.lower() == '.csv':
            return self._parse_csv(file_path)
        elif file_path.suffix.lower() == '.pdf':
            # Use existing DocumentProcessor for PDF
            from skills import DocumentProcessor
            processor = DocumentProcessor()
            # This would need to be implemented based on DocumentProcessor capabilities
            # For now, return empty list as placeholder
            return []
        else:
            raise ValueError("Unsupported file format. Use CSV or PDF.")

    def _parse_csv(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse CSV bank statement."""
        transactions = []
        with open(file_path, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Standardize column names
                date = row.get('date') or row.get('Date') or row.get('DATE')
                description = row.get('description') or row.get('Description') or row.get('DESCRIPTION') or row.get('memo') or row.get('Memo')
                amount_str = row.get('amount') or row.get('Amount') or row.get('AMOUNT')

                if date and description and amount_str:
                    try:
                        # Remove comments from amount string (everything after #)
                        if '#' in amount_str:
                            amount_str = amount_str.split('#')[0].strip()

                        # Parse date
                        parsed_date = None
                        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
                            try:
                                parsed_date = datetime.strptime(date.strip(), fmt)
                                break
                            except ValueError:
                                continue

                        if not parsed_date:
                            continue

                        # Parse amount (handle negatives for withdrawals)
                        amount = float(amount_str.replace('$', '').replace(',', ''))

                        transactions.append({
                            'date': parsed_date.strftime('%Y-%m-%d'),
                            'description': description.strip(),
                            'amount': amount
                        })
                    except (ValueError, AttributeError):
                        continue
        return transactions

    def match_transactions(self, bank_rows: List[Dict[str, Any]], ledger_rows: List[List[Any]], tolerance_days: int = 1) -> Dict[str, Any]:
        """Match bank transactions with ledger transactions."""
        matched = []
        unmatched_bank = []
        unmatched_ledger = []

        # Convert ledger rows to dicts for easier comparison
        ledger_dicts = []
        for row in ledger_rows:
            if len(row) >= 5:
                try:
                    ledger_date_str = str(row[0])
                    ledger_description = str(row[1])
                    ledger_amount_raw = str(row[3])
                    ledger_type = str(row[4]).strip().lower()

                    # Parse amount
                    ledger_amount = float(ledger_amount_raw.replace('$', '').replace(',', ''))

                    # Adjust sign based on transaction type (expenses are negative in bank statements)
                    if ledger_type == "expense":
                        ledger_amount = -ledger_amount
                    # Income stays positive

                    ledger_dicts.append({
                        'date': ledger_date_str,
                        'description': ledger_description,
                        'amount': ledger_amount,
                        'original_row': row
                    })
                except (ValueError, IndexError):
                    continue

        # Match transactions
        matched_ledger_indices = set()

        for bank_tx in bank_rows:
            bank_date = datetime.strptime(bank_tx['date'], '%Y-%m-%d')
            bank_amount = bank_tx['amount']
            bank_desc = bank_tx['description'].lower()

            best_match_idx = None
            best_score = 0

            for i, ledger_tx in enumerate(ledger_dicts):
                if i in matched_ledger_indices:
                    continue

                ledger_date = datetime.strptime(ledger_tx['date'], '%Y-%m-%d')
                ledger_amount = ledger_tx['amount']
                ledger_desc = ledger_tx['description'].lower()

                # Check date tolerance
                date_diff = abs((bank_date - ledger_date).days)
                if date_diff > tolerance_days:
                    continue

                # Check amount exact match
                if abs(bank_amount - ledger_amount) > 0.01:
                    continue

                # Simple description similarity (could be improved)
                desc_match = self._description_similarity(bank_desc, ledger_desc)
                if desc_match > best_score:
                    best_score = desc_match
                    best_match_idx = i

            if best_match_idx is not None and best_score > 0.3:  # Threshold for match
                matched.append({
                    'bank': bank_tx,
                    'ledger': ledger_dicts[best_match_idx]['original_row']
                })
                matched_ledger_indices.add(best_match_idx)
            else:
                unmatched_bank.append(bank_tx)

        # Add unmatched ledger transactions
        for i, ledger_tx in enumerate(ledger_dicts):
            if i not in matched_ledger_indices:
                unmatched_ledger.append(ledger_tx['original_row'])

        return {
            'matched': matched,
            'unmatched_bank': unmatched_bank,
            'unmatched_ledger': unmatched_ledger
        }

    def _description_similarity(self, desc1: str, desc2: str) -> float:
        """Simple similarity score based on common words and abbreviations."""
        # Handle empty descriptions
        if not desc1 or not desc2:
            return 0.0

        desc1_lower = desc1.lower()
        desc2_lower = desc2.lower()

        # Check for exact match
        if desc1_lower == desc2_lower:
            return 1.0

        # Check for substring matches (handles abbreviations like "AWS" in "Amazon Web Services")
        if desc1_lower in desc2_lower or desc2_lower in desc1_lower:
            return 0.8  # High score for substring matches

        # Define common abbreviation mappings
        abbreviation_map = {
            'aws': ['amazon', 'web', 'services'],
            'facebook': ['fb', 'facebook ads'],
            'google': ['goog', 'google ads'],
            'starbucks': ['sbux', 'starbucks coffee'],
            'client': ['client payment', 'client invoice'],
        }

        # Check if either description is an abbreviation of the other
        for full_form, abbreviations in abbreviation_map.items():
            if full_form in desc1_lower:
                for abbrev in abbreviations:
                    if abbrev in desc2_lower:
                        return 0.85
            if full_form in desc2_lower:
                for abbrev in abbreviations:
                    if abbrev in desc1_lower:
                        return 0.85

        # Check for word-level substring matches (e.g., "aws" in "web services")
        words1 = set(desc1_lower.split())
        words2 = set(desc2_lower.split())
        if not words1 or not words2:
            return 0.0

        # Check if any word is a substring of another word
        for w1 in words1:
            for w2 in words2:
                if w1 in w2 or w2 in w1:
                    return 0.7  # Good score for word-level substring matches

        # Check for common word matches
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        jaccard = len(intersection) / len(union) if union else 0.0

        # Boost score if there are common words
        if len(intersection) > 0:
            return max(jaccard, 0.5)  # At least 0.5 if there are common words
        return jaccard

    def compute_difference(self, bank_balance: float, ledger_balance: float) -> float:
        """Compute difference between bank and ledger balances."""
        return bank_balance - ledger_balance