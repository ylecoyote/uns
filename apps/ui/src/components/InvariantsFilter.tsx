/**
 * InvariantsFilter component
 *
 * Filter controls for invariants list.
 * Supports filtering by severity, enforcement_type, status, and search text.
 */

import { useCallback, useState } from 'react';
import type { EnforcementType, InvariantFilters, InvariantSeverity, InvariantStatus } from '../types/invariants';

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

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchText(e.target.value);
    },
    []
  );

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
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex flex-col md:flex-row gap-4">
        {/* Search */}
        <form onSubmit={handleSearchSubmit} className="flex-1">
          <label htmlFor="search" className="sr-only">
            Search invariants
          </label>
          <div className="relative">
            <input
              id="search"
              type="text"
              placeholder="Search invariant statements..."
              value={searchText}
              onChange={handleSearchChange}
              onKeyDown={handleSearchKeyDown}
              className="w-full rounded-lg border border-gray-300 px-4 py-2 pr-10 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              type="submit"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              aria-label="Search"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </button>
          </div>
        </form>

        {/* Severity Filter */}
        <div>
          <label htmlFor="severity" className="sr-only">
            Filter by severity
          </label>
          <select
            id="severity"
            value={filters.severity || ''}
            onChange={handleSeverityChange}
            className="rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {severityOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Enforcement Type Filter */}
        <div>
          <label htmlFor="enforcement_type" className="sr-only">
            Filter by enforcement type
          </label>
          <select
            id="enforcement_type"
            value={filters.enforcement_type || ''}
            onChange={handleEnforcementChange}
            className="rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {enforcementOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Status Filter */}
        <div>
          <label htmlFor="status" className="sr-only">
            Filter by status
          </label>
          <select
            id="status"
            value={filters.status || ''}
            onChange={handleStatusChange}
            className="rounded-lg border border-gray-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {statusOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Clear Filters */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleClearFilters}
            className="rounded-lg border border-gray-300 px-4 py-2 text-gray-600 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
