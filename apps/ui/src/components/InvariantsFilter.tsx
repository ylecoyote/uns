/**
 * InvariantsFilter component — Modernist Modular Filter Bar (1c)
 *
 * Filter controls for invariants list.
 * Supports filtering by severity, enforcement_type, status, and search text.
 */

import { useCallback, useState } from 'react';
import type {
  EnforcementType,
  InvariantFilters,
  InvariantSeverity,
  InvariantStatus,
} from '../types/invariants';

interface InvariantsFilterProps {
  filters: InvariantFilters;
  onFiltersChange: (filters: InvariantFilters) => void;
}

const severityOptions: Array<{ value: InvariantSeverity | ''; label: string }> = [
  { value: '', label: 'All Severities' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
];

const enforcementOptions: Array<{ value: EnforcementType | ''; label: string }> = [
  { value: '', label: 'All Enforcement Types' },
  { value: 'guard', label: 'Guard' },
  { value: 'isolation', label: 'Isolation' },
  { value: 'test', label: 'Test' },
  { value: 'exception', label: 'Exception' },
];

const statusOptions: Array<{ value: InvariantStatus | ''; label: string }> = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

export function InvariantsFilter({ filters, onFiltersChange }: InvariantsFilterProps) {
  const [searchText, setSearchText] = useState(filters.search || '');

  const handleSeverityChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as InvariantSeverity | '';
      onFiltersChange({
        ...filters,
        severity: value || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  const handleEnforcementChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as EnforcementType | '';
      onFiltersChange({
        ...filters,
        enforcement_type: value || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  const handleStatusChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value as InvariantStatus | '';
      onFiltersChange({
        ...filters,
        status: value || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  }, []);

  const handleSearchSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      onFiltersChange({
        ...filters,
        search: searchText || undefined,
      });
    },
    [filters, onFiltersChange, searchText]
  );

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        onFiltersChange({
          ...filters,
          search: searchText || undefined,
        });
      }
    },
    [filters, onFiltersChange, searchText]
  );

  const handleClearFilters = useCallback(() => {
    setSearchText('');
    onFiltersChange({});
  }, [onFiltersChange]);

  const hasActiveFilters =
    filters.severity || filters.enforcement_type || filters.status || filters.search;

  return (
    <div className="invariants-filter-bar">
      {/* Search */}
      <form onSubmit={handleSearchSubmit} className="invariants-filter-cell">
        <label htmlFor="search" className="field-label">
          Search Statements
        </label>
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            id="search"
            type="text"
            className="modernist-input"
            placeholder="Search invariant statements..."
            value={searchText}
            onChange={handleSearchChange}
            onKeyDown={handleSearchKeyDown}
          />
          <button type="submit" className="btn btn-secondary" aria-label="Search">
            Search
          </button>
        </div>
      </form>

      {/* Severity Filter */}
      <div className="invariants-filter-cell">
        <label htmlFor="severity" className="field-label">
          Filter by severity
        </label>
        <select
          id="severity"
          value={filters.severity || ''}
          onChange={handleSeverityChange}
          className="modernist-select"
        >
          {severityOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Enforcement Type Filter */}
      <div className="invariants-filter-cell">
        <label htmlFor="enforcement_type" className="field-label">
          Filter by enforcement type
        </label>
        <select
          id="enforcement_type"
          value={filters.enforcement_type || ''}
          onChange={handleEnforcementChange}
          className="modernist-select"
        >
          {enforcementOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Status Filter */}
      <div className="invariants-filter-cell">
        <label htmlFor="status" className="field-label">
          Filter by status
        </label>
        <select
          id="status"
          value={filters.status || ''}
          onChange={handleStatusChange}
          className="modernist-select"
        >
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Clear Filters */}
      <div className="invariants-filter-cell">
        {hasActiveFilters && (
          <button type="button" onClick={handleClearFilters} className="btn btn-secondary">
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
