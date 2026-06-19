/* eslint-disable @typescript-eslint/no-explicit-any */

import axios, { AxiosRequestConfig } from "axios";
import { api_base_url, NodeExecutor } from "./execution";

export const googleExecutors: Record<string, NodeExecutor> = {

  'send-email': async (input, settings, user_id) => {

    console.log("send email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("send email settings",settingsObj);
    
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
    console.log("send email check:: ",input);

    const response = await axios.post(`${api_base_url}/gmail/send-email`, {
      to:input.to,
      subject:input.subject,
      body:input.body,
    },
    {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
  );

    return {
      success: true,
        data:response.data.message,
        // data: input.to
    };
  },
  'reply-email': async (input, settings, user_id) => {

    console.log("reply email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post('/api/v1/gmail/reply-email', {
      to:input.to,
      subject:input.subject,
      body:input.body,
      original_message_id:input.original_message_id,
    },
        {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
  );
    return {
      success: true,
        data:response.data.message,
    };
  },
  'get-email-details': async (input, settings, user_id) => {

    console.log("reply email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.get(`/api/v1/gmail/messages/${input.message_id}`,
    {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
    );
    return {
      success: true,
        data:response.data.message,
    };
  },
  'create-docs': async (input, settings, user_id) => {

    console.log("reply email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post(`/api/v1/docs/create`,{
      title:input.title,
      initial_content:input.initial_content,
      user_id
    },
          {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
  );
    return {
      success: true,
        data: response.data.documentId,
    };
  },
  'get-docs-content': async (input, settings, user_id) => {

    console.log("reply email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.get(`/api/v1/docs/${input.document_id}/content`,
        {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
    );
    return {
      success: true,
        data:response.data.content,
    };
  },
  'write-docs-content': async (input, settings, user_id) => {

    console.log("reply email:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("write docs input",input);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post(`/api/v1/docs/${input.document_id}/write`,{
      text_content: input.text_content,
      user_id: user_id
    },
          {
      headers: {
        'Authorization': `Bearer ${user_id}`,
      }
    }
  );
    return {
      success: true,
        data:response.data.message,
    };
  },
   'create-drive-folder': async (input, settings, user_id) => {

    console.log("create drive folder:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("create drive settings folder",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post(`/api/v1/drive/folders`,{
      folder_name: input.folder_name,
      parent_id: input.parent_id
    },{
      headers: {
        Authorization: `Bearer ${user_id}`,
      }
    });
    return {
      success: true,
        data:response.data.message,
    };
  },

    'summarise-email': async (input, settings, user_id) => {

    console.log("bg-remover:: ",input);

    const settingsObj = Array.isArray(settings) 
    ? settings.reduce((acc, setting) => {
        acc[setting.id] = setting.default || '';
        return acc;
      }, {} as Record<string, any>)
    : settings;

    console.log("reply email settings",settingsObj);

        let processedInput = input;
    
        // If no input is provided, use the default value from settings
        if (!input && settingsObj.defaultValue) {
          processedInput = settingsObj.defaultValue;
        }
        
        // If a prompt template is provided, use it to format the input
        if (settingsObj.promptTemplate && processedInput) {
          processedInput = settingsObj.promptTemplate.replace(/{{input}}/g, processedInput);
        }
    const response = await axios.post(`/api/v1/mail/summarise`,{
      message_id: input.message_id
    },
  {
      headers: {
        Authorization: `Bearer ${user_id}`,
      }
    }
  );
    return {
      success: true,
        data:response.data.message,
    };
  },
}