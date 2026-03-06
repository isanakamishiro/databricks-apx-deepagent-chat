import { useQuery, useSuspenseQuery, useMutation } from "@tanstack/react-query";
import type { UseQueryOptions, UseSuspenseQueryOptions, UseMutationOptions } from "@tanstack/react-query";
export class ApiError extends Error {
    status: number;
    statusText: string;
    body: unknown;
    constructor(status: number, statusText: string, body: unknown){
        super(`HTTP ${status}: ${statusText}`);
        this.name = "ApiError";
        this.status = status;
        this.statusText = statusText;
        this.body = body;
    }
}
export interface Body_files_upload_api_files_upload_post {
    file: string;
    path: string;
}
export interface ComplexValue {
    display?: string | null;
    primary?: boolean | null;
    ref?: string | null;
    type?: string | null;
    value?: string | null;
}
export interface HTTPValidationError {
    detail?: ValidationError[];
}
export interface MkdirRequest {
    path: string;
}
export interface Name {
    family_name?: string | null;
    given_name?: string | null;
}
export interface SaveChatRequest {
    createdAt: string;
    id: string;
    title: string;
    userId: string;
    visibility?: string;
}
export interface SaveMessagesRequest {
    messages: Record<string, unknown>[];
    userId: string;
}
export interface User {
    active?: boolean | null;
    display_name?: string | null;
    emails?: ComplexValue[] | null;
    entitlements?: ComplexValue[] | null;
    external_id?: string | null;
    groups?: ComplexValue[] | null;
    id?: string | null;
    name?: Name | null;
    roles?: ComplexValue[] | null;
    schemas?: UserSchema[] | null;
    user_name?: string | null;
}
export const UserSchema = {
    "urn:ietf:params:scim:schemas:core:2.0:User": "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:workspace:2.0:User": "urn:ietf:params:scim:schemas:extension:workspace:2.0:User"
} as const;
export type UserSchema = typeof UserSchema[keyof typeof UserSchema];
export interface ValidationError {
    ctx?: Record<string, unknown>;
    input?: unknown;
    loc: (string | number)[];
    msg: string;
    type: string;
}
export interface VersionOut {
    version: string;
}
export const agent_info_endpoint_agent_info_get = async (options?: RequestInit): Promise<{
    data: Record<string, unknown>;
}> =>{
    const res = await fetch("/agent/info", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const agent_info_endpoint_agent_info_getKey = ()=>{
    return [
        "/agent/info"
    ] as const;
};
export function useAgent_info_endpoint_agent_info_get<TData = {
    data: Record<string, unknown>;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: Record<string, unknown>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: agent_info_endpoint_agent_info_getKey(),
        queryFn: ()=>agent_info_endpoint_agent_info_get(),
        ...options?.query
    });
}
export function useAgent_info_endpoint_agent_info_getSuspense<TData = {
    data: Record<string, unknown>;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: Record<string, unknown>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: agent_info_endpoint_agent_info_getKey(),
        queryFn: ()=>agent_info_endpoint_agent_info_get(),
        ...options?.query
    });
}
export const chat = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/chat", {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useChat(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, void>;
}) {
    return useMutation({
        mutationFn: ()=>chat(),
        ...options?.mutation
    });
}
export interface List_chats_api_chat_history_getParams {
    user_id: string;
    limit?: number;
    ending_before?: string | null;
}
export const list_chats_api_chat_history_get = async (params: List_chats_api_chat_history_getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    if (params?.limit != null) searchParams.set("limit", String(params?.limit));
    if (params?.ending_before != null) searchParams.set("ending_before", String(params?.ending_before));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history?${queryString}` : "/api/chat-history";
    const res = await fetch(url, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const list_chats_api_chat_history_getKey = (params?: List_chats_api_chat_history_getParams)=>{
    return [
        "/api/chat-history",
        params
    ] as const;
};
export function useList_chats_api_chat_history_get<TData = {
    data: unknown;
}>(options: {
    params: List_chats_api_chat_history_getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: list_chats_api_chat_history_getKey(options.params),
        queryFn: ()=>list_chats_api_chat_history_get(options.params),
        ...options?.query
    });
}
export function useList_chats_api_chat_history_getSuspense<TData = {
    data: unknown;
}>(options: {
    params: List_chats_api_chat_history_getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: list_chats_api_chat_history_getKey(options.params),
        queryFn: ()=>list_chats_api_chat_history_get(options.params),
        ...options?.query
    });
}
export const save_chat_api_chat_history_post = async (data: SaveChatRequest, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/chat-history", {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useSave_chat_api_chat_history_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, SaveChatRequest>;
}) {
    return useMutation({
        mutationFn: (data)=>save_chat_api_chat_history_post(data),
        ...options?.mutation
    });
}
export interface Get_chat_api_chat_history__chat_id__getParams {
    chat_id: string;
    user_id: string;
}
export const get_chat_api_chat_history__chat_id__get = async (params: Get_chat_api_chat_history__chat_id__getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}?${queryString}` : `/api/chat-history/${params.chat_id}`;
    const res = await fetch(url, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const get_chat_api_chat_history__chat_id__getKey = (params?: Get_chat_api_chat_history__chat_id__getParams)=>{
    return [
        "/api/chat-history/{chat_id}",
        params
    ] as const;
};
export function useGet_chat_api_chat_history__chat_id__get<TData = {
    data: unknown;
}>(options: {
    params: Get_chat_api_chat_history__chat_id__getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: get_chat_api_chat_history__chat_id__getKey(options.params),
        queryFn: ()=>get_chat_api_chat_history__chat_id__get(options.params),
        ...options?.query
    });
}
export function useGet_chat_api_chat_history__chat_id__getSuspense<TData = {
    data: unknown;
}>(options: {
    params: Get_chat_api_chat_history__chat_id__getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: get_chat_api_chat_history__chat_id__getKey(options.params),
        queryFn: ()=>get_chat_api_chat_history__chat_id__get(options.params),
        ...options?.query
    });
}
export interface Delete_chat_api_chat_history__chat_id__deleteParams {
    chat_id: string;
    user_id: string;
}
export const delete_chat_api_chat_history__chat_id__delete = async (params: Delete_chat_api_chat_history__chat_id__deleteParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}?${queryString}` : `/api/chat-history/${params.chat_id}`;
    const res = await fetch(url, {
        ...options,
        method: "DELETE"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useDelete_chat_api_chat_history__chat_id__delete(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: Delete_chat_api_chat_history__chat_id__deleteParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>delete_chat_api_chat_history__chat_id__delete(vars.params),
        ...options?.mutation
    });
}
export interface Get_messages_api_chat_history__chat_id__messages_getParams {
    chat_id: string;
    user_id: string;
}
export const get_messages_api_chat_history__chat_id__messages_get = async (params: Get_messages_api_chat_history__chat_id__messages_getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}/messages?${queryString}` : `/api/chat-history/${params.chat_id}/messages`;
    const res = await fetch(url, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const get_messages_api_chat_history__chat_id__messages_getKey = (params?: Get_messages_api_chat_history__chat_id__messages_getParams)=>{
    return [
        "/api/chat-history/{chat_id}/messages",
        params
    ] as const;
};
export function useGet_messages_api_chat_history__chat_id__messages_get<TData = {
    data: unknown;
}>(options: {
    params: Get_messages_api_chat_history__chat_id__messages_getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: get_messages_api_chat_history__chat_id__messages_getKey(options.params),
        queryFn: ()=>get_messages_api_chat_history__chat_id__messages_get(options.params),
        ...options?.query
    });
}
export function useGet_messages_api_chat_history__chat_id__messages_getSuspense<TData = {
    data: unknown;
}>(options: {
    params: Get_messages_api_chat_history__chat_id__messages_getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: get_messages_api_chat_history__chat_id__messages_getKey(options.params),
        queryFn: ()=>get_messages_api_chat_history__chat_id__messages_get(options.params),
        ...options?.query
    });
}
export interface Save_messages_endpoint_api_chat_history__chat_id__messages_postParams {
    chat_id: string;
}
export const save_messages_endpoint_api_chat_history__chat_id__messages_post = async (params: Save_messages_endpoint_api_chat_history__chat_id__messages_postParams, data: SaveMessagesRequest, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch(`/api/chat-history/${params.chat_id}/messages`, {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useSave_messages_endpoint_api_chat_history__chat_id__messages_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: Save_messages_endpoint_api_chat_history__chat_id__messages_postParams;
        data: SaveMessagesRequest;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>save_messages_endpoint_api_chat_history__chat_id__messages_post(vars.params, vars.data),
        ...options?.mutation
    });
}
export const get_config_api_config_get = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/config", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const get_config_api_config_getKey = ()=>{
    return [
        "/api/config"
    ] as const;
};
export function useGet_config_api_config_get<TData = {
    data: unknown;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: get_config_api_config_getKey(),
        queryFn: ()=>get_config_api_config_get(),
        ...options?.query
    });
}
export function useGet_config_api_config_getSuspense<TData = {
    data: unknown;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: get_config_api_config_getKey(),
        queryFn: ()=>get_config_api_config_get(),
        ...options?.query
    });
}
export interface CurrentUserParams {
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const currentUser = async (params?: CurrentUserParams, options?: RequestInit): Promise<{
    data: User;
}> =>{
    const res = await fetch("/api/current-user", {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const currentUserKey = (params?: CurrentUserParams)=>{
    return [
        "/api/current-user",
        params
    ] as const;
};
export function useCurrentUser<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export function useCurrentUserSuspense<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export interface Files_delete_api_files_delete_deleteParams {
    path: string;
    is_dir?: boolean;
}
export const files_delete_api_files_delete_delete = async (params: Files_delete_api_files_delete_deleteParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.path != null) searchParams.set("path", String(params.path));
    if (params?.is_dir != null) searchParams.set("is_dir", String(params?.is_dir));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/delete?${queryString}` : "/api/files/delete";
    const res = await fetch(url, {
        ...options,
        method: "DELETE"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFiles_delete_api_files_delete_delete(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: Files_delete_api_files_delete_deleteParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>files_delete_api_files_delete_delete(vars.params),
        ...options?.mutation
    });
}
export interface Files_download_api_files_download_getParams {
    path: string;
}
export const files_download_api_files_download_get = async (params: Files_download_api_files_download_getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.path != null) searchParams.set("path", String(params.path));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/download?${queryString}` : "/api/files/download";
    const res = await fetch(url, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const files_download_api_files_download_getKey = (params?: Files_download_api_files_download_getParams)=>{
    return [
        "/api/files/download",
        params
    ] as const;
};
export function useFiles_download_api_files_download_get<TData = {
    data: unknown;
}>(options: {
    params: Files_download_api_files_download_getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: files_download_api_files_download_getKey(options.params),
        queryFn: ()=>files_download_api_files_download_get(options.params),
        ...options?.query
    });
}
export function useFiles_download_api_files_download_getSuspense<TData = {
    data: unknown;
}>(options: {
    params: Files_download_api_files_download_getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: files_download_api_files_download_getKey(options.params),
        queryFn: ()=>files_download_api_files_download_get(options.params),
        ...options?.query
    });
}
export interface Files_list_api_files_list_getParams {
    path?: string;
}
export const files_list_api_files_list_get = async (params?: Files_list_api_files_list_getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params?.path != null) searchParams.set("path", String(params?.path));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/list?${queryString}` : "/api/files/list";
    const res = await fetch(url, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const files_list_api_files_list_getKey = (params?: Files_list_api_files_list_getParams)=>{
    return [
        "/api/files/list",
        params
    ] as const;
};
export function useFiles_list_api_files_list_get<TData = {
    data: unknown;
}>(options?: {
    params?: Files_list_api_files_list_getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: files_list_api_files_list_getKey(options?.params),
        queryFn: ()=>files_list_api_files_list_get(options?.params),
        ...options?.query
    });
}
export function useFiles_list_api_files_list_getSuspense<TData = {
    data: unknown;
}>(options?: {
    params?: Files_list_api_files_list_getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: files_list_api_files_list_getKey(options?.params),
        queryFn: ()=>files_list_api_files_list_get(options?.params),
        ...options?.query
    });
}
export const files_mkdir_api_files_mkdir_post = async (data: MkdirRequest, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/files/mkdir", {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFiles_mkdir_api_files_mkdir_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, MkdirRequest>;
}) {
    return useMutation({
        mutationFn: (data)=>files_mkdir_api_files_mkdir_post(data),
        ...options?.mutation
    });
}
export const files_upload_api_files_upload_post = async (data: FormData, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/files/upload", {
        ...options,
        method: "POST",
        headers: {
            ...options?.headers
        },
        body: data
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFiles_upload_api_files_upload_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, FormData>;
}) {
    return useMutation({
        mutationFn: (data)=>files_upload_api_files_upload_post(data),
        ...options?.mutation
    });
}
export const version = async (options?: RequestInit): Promise<{
    data: VersionOut;
}> =>{
    const res = await fetch("/api/version", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const versionKey = ()=>{
    return [
        "/api/version"
    ] as const;
};
export function useVersion<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
export function useVersionSuspense<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
export const health_check_health_get = async (options?: RequestInit): Promise<{
    data: Record<string, string>;
}> =>{
    const res = await fetch("/health", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const health_check_health_getKey = ()=>{
    return [
        "/health"
    ] as const;
};
export function useHealth_check_health_get<TData = {
    data: Record<string, string>;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: Record<string, string>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: health_check_health_getKey(),
        queryFn: ()=>health_check_health_get(),
        ...options?.query
    });
}
export function useHealth_check_health_getSuspense<TData = {
    data: Record<string, string>;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: Record<string, string>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: health_check_health_getKey(),
        queryFn: ()=>health_check_health_get(),
        ...options?.query
    });
}
export const invocations_endpoint_invocations_post = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/invocations", {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useInvocations_endpoint_invocations_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, void>;
}) {
    return useMutation({
        mutationFn: ()=>invocations_endpoint_invocations_post(),
        ...options?.mutation
    });
}
export const responses_endpoint_responses_post = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/responses", {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useResponses_endpoint_responses_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, void>;
}) {
    return useMutation({
        mutationFn: ()=>responses_endpoint_responses_post(),
        ...options?.mutation
    });
}
