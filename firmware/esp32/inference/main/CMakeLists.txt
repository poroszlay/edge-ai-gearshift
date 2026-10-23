idf_component_register(SRCS "main.cc" "device.cc" "reference_fc.cc" INCLUDE_DIRS "." "${CMAKE_CURRENT_BINARY_DIR}"
    REQUIRES measurement json esp_timer esp_driver_uart esp_system)
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=DebugLog")
if(NOT CMAKE_BUILD_EARLY_EXPANSION)
    # Match the frozen PC BUILTIN_REF requantization; ESP-NN FC uses a
    # different double-rounding path, so FC is explicitly registered above
    # from the pinned upstream reference source.
    idf_component_get_property(TFLM_LIB espressif__esp-tflite-micro COMPONENT_LIB)
    target_compile_definitions(${TFLM_LIB} PRIVATE TFLITE_SINGLE_ROUNDING=1)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE TFLITE_SINGLE_ROUNDING=1)
    get_filename_component(REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
    if(NOT DEFINED GEARSHIFT_MODEL_DIR)
        set(GEARSHIFT_MODEL_DIR "${REPO_ROOT}/models/mlp-v2")
    endif()
    file(GLOB MODEL_FILES "${GEARSHIFT_MODEL_DIR}/*")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${MODEL_FILES}
        "${REPO_ROOT}/tools/embed-model.py" "${REPO_ROOT}/gearshift/frozen_export.py")
    execute_process(COMMAND "${PYTHON}" "${REPO_ROOT}/tools/embed-model.py"
        "${GEARSHIFT_MODEL_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/model_data.h"
        RESULT_VARIABLE EMBED_RESULT)
    if(NOT EMBED_RESULT EQUAL 0)
        message(FATAL_ERROR "Frozen model verification/embedding failed")
    endif()
endif()
