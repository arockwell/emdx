#!/usr/bin/env fish

# Fish wrapper for the Python copy tool
# Makes it easier to use with fish-friendly syntax and modern utilities

function copy_py --description "Copy Python classes and functions between files"
    set -l TOOL_PATH (dirname (status --current-filename))/copy_tool.py
    
    # Check if the Python tool exists
    if not test -f $TOOL_PATH
        echo "❌ Python copy tool not found at $TOOL_PATH"
        echo "Make sure copy_tool.py is in the same directory as this script"
        return 1
    end
    
    # Parse arguments
    set -l command $argv[1]
    
    switch $command
        case class cls
            if test (count $argv) -lt 4
                echo "Usage: copy_py class SOURCE_FILE TARGET_FILE CLASS_NAME"
                echo "Example: copy_py class old.py new.py MyClass"
                return 1
            end
            python $TOOL_PATH copy-class $argv[2] $argv[3] $argv[4]
            
        case function func fn
            if test (count $argv) -lt 4
                echo "Usage: copy_py function SOURCE_FILE TARGET_FILE FUNCTION_NAME"
                echo "Example: copy_py function old.py new.py my_function"
                return 1
            end
            python $TOOL_PATH copy-function $argv[2] $argv[3] $argv[4]
            
        case extract multi
            if test (count $argv) -lt 4
                echo "Usage: copy_py extract SOURCE_FILE TARGET_DIR CLASS1 [CLASS2 ...]"
                echo "Example: copy_py extract big.py modules/ Class1 Class2 Class3"
                return 1
            end
            python $TOOL_PATH extract-classes $argv[2..-1]
            
        case analyze info inspect
            if test (count $argv) -lt 2
                echo "Usage: copy_py analyze FILE"
                echo "Example: copy_py analyze big_file.py"
                return 1
            end
            python $TOOL_PATH analyze $argv[2]
            
        case help -h --help
            echo "🐍 Python Copy Tool - Fish Wrapper"
            echo ""
            echo "Commands:"
            echo "  class     Copy a class between files"
            echo "  function  Copy a function between files" 
            echo "  extract   Extract multiple classes to separate files"
            echo "  analyze   Analyze a Python file"
            echo "  help      Show this help"
            echo ""
            echo "Examples:"
            echo "  copy_py class textual_browser.py text_areas.py SelectionTextArea"
            echo "  copy_py function utils.py helpers.py my_helper"
            echo "  copy_py extract big_file.py modules/ Class1 Class2 Class3"
            echo "  copy_py analyze textual_browser.py"
            
        case ""
            echo "Usage: copy_py COMMAND [args...]"
            echo "Run 'copy_py help' for more information"
            return 1
            
        case "*"
            echo "❌ Unknown command: $command"
            echo "Run 'copy_py help' for available commands"
            return 1
    end
end

# Quick aliases for common operations
function analyze_py --description "Analyze a Python file"
    copy_py analyze $argv
end

function extract_classes --description "Extract classes to separate files"
    copy_py extract $argv
end

# EMDX-specific helper functions
function fix_emdx_browser --description "Fix EMDX main_browser.py refactoring"
    echo "🏗️  EMDX Browser Refactoring Helper"
    echo "==================================="
    
    # Check if we're in an EMDX project
    if not test -f emdx/ui/main_browser.py
        echo "❌ Not in EMDX project root (no emdx/ui/main_browser.py found)"
        return 1
    end
    
    echo "📁 Found EMDX project structure"
    
    # Analyze the current main_browser.py
    echo ""
    echo "🔍 Analyzing current main_browser.py..."
    copy_py analyze emdx/ui/main_browser.py
    
    echo ""
    echo "🎯 Suggested refactoring operations:"
    echo ""
    
    # Map of target files and their expected classes
    set -l extractions \
        "emdx/ui/vim_editor.py:VimEditTextArea" \
        "emdx/ui/selection_area.py:SelectionTextArea" \
        "emdx/ui/title_input.py:TitleInput" \
        "emdx/ui/doc_viewer.py:FullScreenView" \
        "emdx/ui/delete_modal.py:DeleteConfirmScreen" \
        "emdx/ui/search_results.py:SearchResultsTable" \
        "emdx/ui/browser_modes.py:BrowserModeHandler"
    
    for extraction in $extractions
        set -l parts (string split ":" $extraction)
        set -l target_file $parts[1]
        set -l classes (string split "," $parts[2])
        
        echo "📋 $target_file"
        for class_name in $classes
            if test -f $target_file
                echo "  ✅ $class_name (file exists - check if class is there)"
            else
                echo "  📝 $class_name (needs extraction)"
                echo "     → copy_py class emdx/ui/main_browser.py $target_file $class_name"
            end
        end
        echo ""
    end
    
    echo "💡 To run all extractions automatically, use:"
    echo "   extract_emdx_classes"
end

function extract_emdx_classes --description "Extract all EMDX classes automatically"
    echo "🚀 Auto-extracting EMDX classes..."
    
    # Define the extractions
    set -l extractions \
        "emdx/ui/vim_editor.py:VimEditTextArea" \
        "emdx/ui/selection_area.py:SelectionTextArea" \
        "emdx/ui/title_input.py:TitleInput" \
        "emdx/ui/doc_viewer.py:FullScreenView" \
        "emdx/ui/delete_modal.py:DeleteConfirmScreen"
    
    set -l success_count 0
    set -l total_count (count $extractions)
    
    for extraction in $extractions
        set -l parts (string split ":" $extraction)
        set -l target_file $parts[1]
        set -l class_name $parts[2]
        
        echo "📦 Extracting $class_name → $target_file"
        
        if copy_py class emdx/ui/main_browser.py $target_file $class_name
            set success_count (math $success_count + 1)
            echo "✅ Success"
        else
            echo "❌ Failed"
        end
        echo ""
    end
    
    echo "📊 Extraction complete: $success_count/$total_count succeeded"
    
    if test $success_count -eq $total_count
        echo ""
        echo "🎉 All extractions successful!"
        echo "Next steps:"
        echo "1. Update main_browser.py imports"
        echo "2. Test with: emdx --help"
        echo "3. Create a BrowserModeRouter to handle mode switching"
    end
end

# Modern fish-friendly utilities
function find_python_classes --description "Find all Python classes in a directory using fd and rg"
    set -l search_dir $argv[1]
    if test -z "$search_dir"
        set search_dir .
    end
    
    echo "🔍 Finding Python classes in $search_dir"
    
    # Use fd to find Python files, then rg to find class definitions
    fd -e py . $search_dir | while read -l py_file
        set -l classes (rg "^class\s+(\w+)" -o -r '$1' $py_file 2>/dev/null)
        if test -n "$classes"
            echo "📄 $py_file"
            for class_name in $classes
                echo "  🏗️  $class_name"
            end
        end
    end
end

function find_python_functions --description "Find all Python functions in a directory using fd and rg"
    set -l search_dir $argv[1]
    if test -z "$search_dir"
        set search_dir .
    end
    
    echo "🔍 Finding Python functions in $search_dir"
    
    # Use fd to find Python files, then rg to find function definitions
    fd -e py . $search_dir | while read -l py_file
        set -l functions (rg "^def\s+(\w+)" -o -r '$1' $py_file 2>/dev/null)
        if test -n "$functions"
            echo "📄 $py_file"
            for func_name in $functions
                echo "  ⚙️  $func_name"
            end
        end
    end
end

# Install function
function install_copy_py --description "Install the copy_py tools to ~/.local/bin"
    set -l install_dir ~/.local/bin
    set -l script_dir (dirname (status --current-filename))
    
    mkdir -p $install_dir
    
    # Copy the Python tool
    if test -f $script_dir/copy_tool.py
        cp $script_dir/copy_tool.py $install_dir/
        chmod +x $install_dir/copy_tool.py
        echo "✅ Installed copy_tool.py to $install_dir"
    else
        echo "❌ copy_tool.py not found in $script_dir"
        return 1
    end
    
    # Copy this fish script
    cp (status --current-filename) $install_dir/copy_py.fish
    chmod +x $install_dir/copy_py.fish
    echo "✅ Installed copy_py.fish to $install_dir"
    
    echo ""
    echo "🎉 Installation complete!"
    echo "Add to your fish config:"
    echo "  source ~/.local/bin/copy_py.fish"
    echo ""
    echo "Or add ~/.local/bin to your PATH and run:"
    echo "  copy_py help"
end

# Export the main function
if test (basename (status --current-filename)) = "copy_py.fish"
    # If this script is being sourced, export the functions
    echo "🐍 Python Copy Tool loaded"
    echo "Usage: copy_py COMMAND [args...]"
    echo "Help:  copy_py help"
end