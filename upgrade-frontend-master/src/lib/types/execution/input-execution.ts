
/* eslint-disable @typescript-eslint/no-explicit-any */
import { NodeExecutor } from "./execution";

export const inputExecutors: Record<string, NodeExecutor> = {
  'user-input': async (input, settings) => {
    // The log output shows that settings is an array of configuration objects
    // We need to convert it to an object with keys based on the 'id' property
    const settingsObj = Array.isArray(settings) 
      ? settings.reduce((acc, setting) => {
          acc[setting.id] = setting.default || '';
          return acc;
        }, {} as Record<string, any>)
      : settings;

      console.log("user-input update settings check:: ",settingsObj);
    
    // Handle user input based on settings
    let processedInput = input;
    
    // If no input is provided, use the default value from settings
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    
    // If a prompt template is provided, use it to format the input
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }
    
    // Return processed input as a prompt
    return {
      success: true,
      data: settingsObj.inputLabel,
    };
  },
 'file-input': async (input, settings) => {
    // The log output shows that settings is an array of configuration objects
    // We need to convert it to an object with keys based on the 'id' property
    const settingsObj = Array.isArray(settings) 
      ? settings.reduce((acc, setting) => {
          acc[setting.id] = setting.default || '';
          return acc;
        }, {} as Record<string, any>)
      : settings;

      console.log("user-input update settings check:: ",settingsObj);
    
    // Handle user input based on settings
    let processedInput = input;
    
    // If no input is provided, use the default value from settings
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    
    // If a prompt template is provided, use it to format the input
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }
    
    // Return processed input as a prompt
    return {
      success: true,
      data: settingsObj.file,
    };
  },

  'api-input': async (input, settings) => {
    // The log output shows that settings is an array of configuration objects
    // We need to convert it to an object with keys based on the 'id' property
    const settingsObj = Array.isArray(settings) 
      ? settings.reduce((acc, setting) => {
          acc[setting.id] = setting.default || '';
          return acc;
        }, {} as Record<string, any>)
      : settings;

      console.log("api-input update settings check:: ",settingsObj);
    
    // Handle user input based on settings
    let processedInput = input;
    
    // If no input is provided, use the default value from settings
    if (!input && settingsObj.defaultValue) {
      processedInput = settingsObj.defaultValue;
    }
    
    // If a prompt template is provided, use it to format the input
    if (settingsObj.promptTemplate && processedInput) {
      processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
    }
    
    // Return processed input as a prompt
    return {
      success: true,
      data: settingsObj.apiInputLabel,
    };
  },
}