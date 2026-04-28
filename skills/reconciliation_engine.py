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
                        # Parse date
                        parsed_date = None
                        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
                            try:
                                parsed_date = datetime.strptime(date, fmt)
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
                    ledger_dicts.append({
                        'date': str(row[0]),
                        'description': str(row[1]),
                        'amount': float(str(row[3]).replace('$', '').replace(',', '')),
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

            if best_match_idx is not None and best_score > 0.5:  # Threshold for match
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
        """Simple similarity score based on common words."""
        words1 = set(desc1.split())
        words2 = set(desc2.split())
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union) if union else 0.0

    def compute_difference(self, bank_balance: float, ledger_balance: float) -> float:
        """Compute difference between bank and ledger balances."""
        return bank_balance - ledger_balance