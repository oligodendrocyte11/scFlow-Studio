# Force project logs and R warnings to English when the system supports it.
.scflow_set_english_locale <- function() {
  Sys.setenv(LANGUAGE = "en", LANG = "en_US.UTF-8")
  for (loc in c("en_US.UTF-8", "C.UTF-8", "C")) {
    ok <- tryCatch({
      res <- suppressWarnings(Sys.setlocale("LC_MESSAGES", loc))
      !is.na(res) && nzchar(res)
    }, error = function(e) FALSE)
    if (isTRUE(ok)) break
  }
}
.scflow_set_english_locale()

# ═══════════════════════════════════════════
# io_utils.R — I/Ohelper functions
# ═══════════════════════════════════════════

# %||% fallback(rlang)
if (!exists("%||%")) {
  `%||%` <- function(x, y) if (is.null(x)) y else x
}

# ──────────────────────────────────────────
# Loading JSON Parameters
#
#: simplifyDataFrame = FALSE
# → params$samples list-of-lists
# → jsonlite data.frame
# → Parameters(min_ncount = 500)
# ──────────────────────────────────────────
read_params <- function(params_path) {
  if (!file.exists(params_path)) {
    stop(paste("Parameter file does not exist:", params_path))
  }

  params <- jsonlite::fromJSON(
    params_path,
 simplifyVector = TRUE, # 
 simplifyDataFrame = FALSE, # [{},{}] data.frame
 simplifyMatrix = FALSE # matrix
  )

 #: Parameters
  cat("── Parameter overview ──\n")
  cat(sprintf("  Parameter file: %s\n", params_path))
  cat(sprintf("  Top-level fields: %s\n", paste(names(params), collapse = ", ")))
  if (!is.null(params$samples)) {
    cat(sprintf("  samples type: %s\n", paste(class(params$samples), collapse = "/")))
    cat(sprintf("  samples length: %d\n", length(params$samples)))
  }
  cat("──────────────\n")

  return(params)
}

# ──────────────────────────────────────────
# Parameters(NULL list)
# ──────────────────────────────────────────
safe_param <- function(params, key, default = NULL) {
  val <- params[[key]]
  if (is.null(val)) return(default)
 # jsonlite length 1 list, 
  if (is.list(val) && length(val) == 1) return(val[[1]])
  return(val)
}

# ──────────────────────────────────────────
# Sample List
# jsonlite, list-of-lists
# named list: list(name="x", group="y",..)
# ──────────────────────────────────────────
safe_samples <- function(samples_raw) {
  if (is.null(samples_raw)) {
    stop("The parameters are missing the samples field. Please check the Project and Data page.")
  }

 # Case1: list-of-lists(Case, simplifyDataFrame=FALSE)
  if (is.list(samples_raw) && !is.data.frame(samples_raw)) {
 # Sample named list: list(name="x", group="y")
    if (!is.null(names(samples_raw)) && "name" %in% names(samples_raw)) {
    cat("  [safe_samples] Detected one sample record; wrapping it as a list.\n")
      return(list(samples_raw))
    }
    return(samples_raw)
  }

 # Case2: jsonlite data.frame(simplifyDataFrame=TRUE)
  if (is.data.frame(samples_raw)) {
 cat(" [safe_samples] Detected samples data.frame, automatically converted list-of-lists\n")
    result <- list()
    for (i in 1:nrow(samples_raw)) {
      result[[i]] <- as.list(samples_raw[i, , drop = FALSE])
    }
    return(result)
  }

 # Case3: 
  stop(paste0(
    "Invalid samples field format; unable to parse.\n",
 " Expected: JSON [{\"name\":.., \"group\":..},..]\n",
    "  Actual type: ", paste(class(samples_raw), collapse = "/"), "\n",
    "  Actual content: ", capture.output(str(samples_raw))[1], "\n",
    "  Please check the Python parameter payload."
  ))
}

# ──────────────────────────────────────────
# summary.json
# ──────────────────────────────────────────
write_summary <- function(summary_list, output_dir) {
  path <- file.path(output_dir, "summary.json")
  jsonlite::write_json(summary_list, path, auto_unbox = TRUE, pretty = TRUE)
  cat(sprintf("##SUMMARY:%s\n", path))
}

# Error summary(Suggestion)
write_error_summary <- function(step, message, suggestion, output_dir) {
  summary <- list(
    status = "error",
    step = step,
    message = message,
    suggestion = suggestion
  )
  write_summary(summary, output_dir)
}

# exists
ensure_dir <- function(path) {
  if (!dir.exists(path)) {
    dir.create(path, recursive = TRUE)
  }
}


safe_find_clusters <- function(obj, resolution, random_seed = 1234, verbose = FALSE) {
  tryCatch({
    FindClusters(obj, resolution = resolution, algorithm = 1, random.seed = as.integer(random_seed), verbose = verbose)
  }, error = function(e) {
    cat(sprintf("  FindClusters algorithm=1 failed, fallback to default algorithm: %s\n", conditionMessage(e)))
    FindClusters(obj, resolution = resolution, random.seed = as.integer(random_seed), verbose = verbose)
  })
}
