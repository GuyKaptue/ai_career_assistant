/**
 * Shared frontend contracts. These typedefs mirror the backend
 * Pydantic schemas in `backend/app/api/schemas.py` so the UI
 * and the API stay in sync without a code generator.
 */

/**
 * @typedef {Object} Template
 * @property {string} id
 * @property {string} name
 * @property {'cv'|'cover_letter'|'resignation'} document_type
 * @property {string} [description]
 * @property {string[]} [supported_locales]
 */

/**
 * @typedef {Object} TemplatePreview
 * @property {string} template_id
 * @property {string} document_type
 * @property {string} locale
 * @property {string} name
 * @property {boolean} ai_generated
 * @property {boolean} review_before_sending
 * @property {string} content
 */

/**
 * @typedef {Object} JobApplication
 * @property {string} id
 * @property {string} user_id
 * @property {string} company
 * @property {string} position
 * @property {'applied'|'interview'|'offer'|'rejected'} [status]
 * @property {string} [job_url]
 * @property {string} [notes]
 * @property {string} [follow_up_date]
 * @property {string} [created_at]
 * @property {string} [updated_at]
 */

/**
 * @typedef {Object} JobSearchResult
 * @property {string} title
 * @property {string} company
 * @property {string} [location]
 * @property {string} [url]
 */

/**
 * @typedef {Object} AtsCheckResult
 * @property {number} score
 * @property {string[]} [matched_keywords]
 * @property {string[]} [missing_keywords]
 */

/**
 * @typedef {Object} GenerationResult
 * @property {string} [summary]
 * @property {string} [content]
 * @property {string} [template_id]
 * @property {boolean} [ai_generated]
 */

/** @typedef {'idle'|'loading'|'success'|'error'} AsyncPhase */

/**
 * @template T
 * @typedef {Object} AsyncState
 * @property {AsyncPhase} phase
 * @property {T|null} data
 * @property {Error|null} error
 */
